"""API FastAPI : expose le pipeline Phase 1 (tms_vision.pipeline) pour la
capture web. Reçoit un clip vidéo (enregistré dans le navigateur en un seul
POST /analyses, ou importé et envoyé par chunks via POST /uploads + PUT
.../chunks/{index} + POST .../complete), lance l'analyse RULA existante,
persiste le résultat en DuckDB (tms_vision.storage) et renvoie le résumé +
les liens vers les ressources produites (voir
docs/superpowers/specs/2026-09-14-web-capture-fastapi-design.md,
docs/superpowers/specs/2026-09-15-web-upload-chunked-design.md et
docs/superpowers/specs/2026-09-22-duckdb-analysis-storage-design.md)."""
import json
import os
import re
import secrets
import shutil
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import cv2
from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from tms_vision import (
    assistant, bilan, capsule_build, exercises, library, mailer, metiers, recurrence, storage, version,
)
from tms_vision.load import bounds, parse_load
from tms_vision.capsules import CAPSULES, DEFAULT_PROGRAM_SIZE, MAX_PROGRAM_SIZE
from tms_vision.program import (
    build_analysis_program, build_bilan_program, select_program,
)
from tms_vision.rescore import rescore_frames, summarize_for_load
from tms_vision.pipeline import analyze_video, generate_run_id
from tms_vision.pose3d_export import build_pose3d_payload

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Garde-fou mémoire : analyze_video() garde toutes les frames décodées en
# mémoire pour tout traiter par lots (voir pipeline.py). Sans ce garde-fou,
# une vidéo HD/4K longue importée par upload (qui n'a pas la limite
# 640x480/30s imposée à la capture caméra) peut faire monter le process à
# plusieurs Go de RAM. Seuil choisi à partir d'une mesure empirique (revue
# finale de la tranche 2) : ~6.4 Mo par frame en 1080p.
MAX_ESTIMATED_MEMORY_BYTES = 2 * 1024**3  # 2 Gio

# Par défaut, seul le serveur de dev Next.js local est autorisé. Pour tester
# depuis un autre appareil (ex. iPhone via un tunnel HTTPS), surcharger avec
# ALLOWED_ORIGINS="https://mon-tunnel.trycloudflare.com" (une ou plusieurs
# origines séparées par des virgules) avant de lancer uvicorn.
_default_origins = "http://localhost:3000"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", _default_origins).split(",")
    if origin.strip()
]

# Une session d'envoi abandonnée (jamais terminée) laisse sur le disque les morceaux de la vidéo
# BRUTE, visages nets : on les supprime au bout de ce délai sans activité.
UPLOAD_SESSION_MAX_AGE_SECONDS = 24 * 3600


def _purge_stale_upload_sessions() -> int:
    """Supprime les sessions d'envoi (OUTPUT_DIR/.uploads/<uuid>) sans activité depuis plus de
    UPLOAD_SESSION_MAX_AGE_SECONDS ; l'activité est la date de modification la plus récente du
    dossier et de ses morceaux. Ne touche qu'aux dossiers nommés comme un uuid, jamais au reste.
    Retourne le nombre de sessions supprimées."""
    root = OUTPUT_DIR / ".uploads"
    if not root.is_dir():
        return 0

    removed = 0
    now = time.time()
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        try:
            uuid.UUID(entry.name)
        except ValueError:
            continue
        last_activity = max([entry.stat().st_mtime, *(p.stat().st_mtime for p in entry.iterdir())])
        if now - last_activity > UPLOAD_SESSION_MAX_AGE_SECONDS:
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
    return removed


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _purge_stale_upload_sessions()
    yield


app = FastAPI(lifespan=_lifespan)
app.include_router(assistant.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    # GET est volontairement absent : une requête GET "simple" (sans en-tête
    # personnalisé) ne déclenche pas de preflight CORS, donc pas besoin de la
    # lister ici -- ça vaut pour les routes GET /analyses/... (vidéo/CSV/
    # pose3D) comme ça valait pour l'ancienne route GET /outputs/{filename}.
    # DELETE : suppression d'une fiche d'activité et d'un modèle de métier depuis le site.
    allow_methods=["POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


def _reject_if_estimated_too_large(video_path: Path) -> None:
    capture = cv2.VideoCapture(str(video_path))
    try:
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    finally:
        capture.release()

    estimated_bytes = frame_count * width * height * 3 * 2
    if estimated_bytes > MAX_ESTIMATED_MEMORY_BYTES:
        raise HTTPException(
            status_code=422,
            detail=(
                "Vidéo trop volumineuse pour être analysée (résolution et/ou durée trop "
                "élevées pour la mémoire disponible du serveur). Réduisez la résolution ou "
                "la durée du clip."
            ),
        )


async def _analyze_and_build_response(
    video_path: Path,
    side: str,
    load_kg: float,
    wrist_twist: str,
    worker_label: str | None,
    poste_label: str | None,
) -> dict:
    """Appelle analyze_video sur un fichier déjà sur disque, persiste le
    résultat en DuckDB et construit la réponse JSON standard. Partagé par
    create_analysis (upload direct) et complete_upload (upload par chunks) :
    les deux finissent par produire un seul fichier vidéo local, traité de
    façon identique à partir de ce point."""
    _reject_if_estimated_too_large(video_path)
    try:
        result = await run_in_threadpool(
            analyze_video, source=str(video_path), side=side, load_kg=load_kg,
            wrist_twist=wrist_twist,
        )
    except (FileNotFoundError, RuntimeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if result.empty:
        raise HTTPException(
            status_code=422,
            detail="Vidéo illisible ou vide : aucune frame n'a pu être extraite.",
        )

    analysis_id = generate_run_id()
    pose3d_json = json.dumps(build_pose3d_payload(result.pose3d_records), ensure_ascii=False)
    # storage.save_analysis (comme list_analyses/get_analysis plus bas) est un
    # appel DuckDB bloquant exécuté ici de façon synchrone dans un handler
    # async def -- ça bloque la boucle événementielle asyncio le temps de la
    # requête SQL. Sans conséquence à l'échelle actuelle du projet (un seul
    # utilisateur), mais si la concurrence augmente, l'enrober avec
    # run_in_threadpool (comme analyze_video ci-dessus) serait sûr : DuckDB
    # supporte plusieurs connexions concurrentes en-process vers le même
    # fichier.
    storage.save_analysis(
        analysis_id=analysis_id,
        created_at=datetime.now(timezone.utc),
        side=side, load_kg=load_kg, wrist_twist=wrist_twist,
        worker_label=worker_label, poste_label=poste_label,
        summary=result.summary, video_bytes=result.video_bytes, pose3d_json=pose3d_json,
        frame_rows=result.frame_rows,
    )

    return {
        "analysis_id": analysis_id,
        "summary": result.summary,
        "annotated_video_url": f"/analyses/{analysis_id}/video",
        "csv_url": f"/analyses/{analysis_id}/frames.csv",
        "pose3d_url": f"/analyses/{analysis_id}/pose3d",
        "side": side,
    }


@app.post("/analyses")
async def create_analysis(
    file: UploadFile = File(...),
    side: Literal["left", "right"] = Form(...),
    load_kg: float = Form(0.0, ge=0),
    wrist_twist: Literal["normal", "extreme"] = Form(...),
    worker_label: str | None = Form(None, max_length=200),
    poste_label: str | None = Form(None, max_length=200),
) -> dict:
    suffix = Path(file.filename or "").suffix or ".webm"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    upload_path = Path(tmp.name)
    try:
        with tmp:
            shutil.copyfileobj(file.file, tmp)
        return await _analyze_and_build_response(
            upload_path, side, load_kg, wrist_twist, worker_label, poste_label
        )
    finally:
        upload_path.unlink(missing_ok=True)


@app.post("/uploads")
async def start_upload(
    filename: str = Form(...),
    total_chunks: int = Form(..., ge=1, le=10000),
) -> dict:
    """Démarre une session d'upload par chunks. L'état de la session vit
    entièrement sur le système de fichiers (meta.json + fichiers chunk_NNNNNN
    écrits par upload_chunk/complete_upload) : pas de dict en mémoire, pour
    survivre à un redémarrage d'uvicorn --reload en cours d'upload. C'est un
    état transitoire de transport, pas un résultat d'analyse -- il reste
    hors DuckDB, voir docs/superpowers/specs/2026-09-22-duckdb-analysis-storage-design.md."""
    _purge_stale_upload_sessions()
    upload_id = uuid.uuid4().hex
    session_dir = OUTPUT_DIR / ".uploads" / upload_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "meta.json").write_text(
        json.dumps({"filename": filename, "total_chunks": total_chunks})
    )
    return {"upload_id": upload_id}


def _resolve_session_dir(upload_id: str) -> Path:
    try:
        uuid.UUID(upload_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Session d'envoi introuvable.") from error
    return OUTPUT_DIR / ".uploads" / upload_id


@app.put("/uploads/{upload_id}/chunks/{index}")
async def upload_chunk(upload_id: str, index: int, file: UploadFile = File(...)) -> dict:
    session_dir = _resolve_session_dir(upload_id)
    meta_path = session_dir / "meta.json"
    if not meta_path.is_file():
        raise HTTPException(status_code=404, detail="Session d'envoi introuvable.")

    total_chunks = json.loads(meta_path.read_text())["total_chunks"]
    if not 0 <= index < total_chunks:
        raise HTTPException(status_code=400, detail="Index de morceau hors limites.")

    chunk_path = session_dir / f"chunk_{index:06d}"
    with open(chunk_path, "wb") as chunk_file:
        shutil.copyfileobj(file.file, chunk_file)

    return {"received": index}


@app.post("/uploads/{upload_id}/complete")
async def complete_upload(
    upload_id: str,
    side: Literal["left", "right"] = Form(...),
    load_kg: float = Form(0.0, ge=0),
    wrist_twist: Literal["normal", "extreme"] = Form(...),
    worker_label: str | None = Form(None, max_length=200),
    poste_label: str | None = Form(None, max_length=200),
) -> dict:
    session_dir = _resolve_session_dir(upload_id)
    meta_path = session_dir / "meta.json"
    if not meta_path.is_file():
        raise HTTPException(status_code=404, detail="Session d'envoi introuvable.")

    meta = json.loads(meta_path.read_text())
    total_chunks = meta["total_chunks"]
    chunk_paths = [session_dir / f"chunk_{i:06d}" for i in range(total_chunks)]
    missing = [i for i, path in enumerate(chunk_paths) if not path.is_file()]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Morceau(x) manquant(s) : {missing}. Réessayez l'import du fichier.",
        )

    suffix = Path(meta["filename"]).suffix or ".webm"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    upload_path = Path(tmp.name)
    try:
        with tmp:
            for chunk_path in chunk_paths:
                with open(chunk_path, "rb") as chunk_file:
                    shutil.copyfileobj(chunk_file, tmp)
        return await _analyze_and_build_response(
            upload_path, side, load_kg, wrist_twist, worker_label, poste_label
        )
    finally:
        upload_path.unlink(missing_ok=True)
        shutil.rmtree(session_dir, ignore_errors=True)


@app.get("/analyses")
async def list_analyses(
    worker_label: str | None = None,
    poste_label: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[dict]:
    return storage.list_analyses(
        worker_label=worker_label, poste_label=poste_label, since=since, until=until
    )


@app.get("/analyses/{analysis_id}")
async def get_analysis(analysis_id: str) -> dict:
    analysis = storage.get_analysis(analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analyse introuvable.")
    return analysis


def _parse_single_byte_range(range_header: str, total_length: int) -> tuple[int, int] | None:
    """Parse un unique intervalle "bytes=START-END" (RFC 7233 §2.1 -- un seul
    range, END facultatif). Retourne (start, end) inclusifs quand l'en-tête
    suit cette syntaxe ; None si l'en-tête ne suit pas du tout la syntaxe
    "bytes=..." attendue (dans ce cas l'appelant doit l'ignorer et servir le
    contenu complet, comportement RFC pour un Range mal formé -- on ne gère
    pas le multi-range, absent des clients vidéo qui nous intéressent ici).
    Lève ValueError si la syntaxe est valide mais l'intervalle insatisfiable
    (-> 416 côté appelant)."""
    if not range_header.startswith("bytes="):
        return None
    spec = range_header[len("bytes="):]
    if "," in spec or "-" not in spec:
        return None

    start_str, _, end_str = spec.partition("-")
    if start_str == "" and end_str == "":
        return None

    if start_str == "":
        # Range suffixe ("bytes=-500" = les 500 derniers octets).
        if not end_str.isdigit():
            return None
        suffix_length = int(end_str)
        if suffix_length <= 0:
            raise ValueError("Intervalle insatisfiable.")
        start = max(total_length - suffix_length, 0)
        end = total_length - 1
    else:
        if not start_str.isdigit():
            return None
        start = int(start_str)
        if end_str == "":
            end = total_length - 1
        elif end_str.isdigit():
            end = int(end_str)
        else:
            return None

    if start > end:
        # Syntaxiquement invalide (RFC 7233 §2.1 : last-byte-pos < first-byte-pos),
        # pas insatisfiable -- l'appelant doit l'ignorer et servir le contenu
        # complet (même traitement que les autres cas de syntaxe invalide
        # ci-dessus), pas répondre 416.
        return None
    if start >= total_length:
        raise ValueError("Intervalle insatisfiable.")
    return start, min(end, total_length - 1)


def _video_response(
    video_bytes: bytes, content_disposition: str, range_header: str | None
) -> Response:
    """Réponse vidéo avec support des requêtes HTTP Range (RFC 7233, un seul
    intervalle) -- nécessaire pour que <video> fonctionne de façon fiable sur iOS
    Safari (voir skill iphone-tunnel-test), qui s'appuie sur Range pour le seek et
    le pré-chargement progressif. Partagée par la vidéo annotée d'une analyse
    (octets venant de DuckDB) et par les vidéos d'exercices générées."""
    total_length = len(video_bytes)
    headers = {"Content-Disposition": content_disposition, "Accept-Ranges": "bytes"}

    if range_header is not None:
        try:
            parsed_range = _parse_single_byte_range(range_header, total_length)
        except ValueError:
            return Response(
                status_code=416,
                headers={**headers, "Content-Range": f"bytes */{total_length}"},
            )
        if parsed_range is not None:
            start, end = parsed_range
            chunk = video_bytes[start : end + 1]
            return Response(
                content=chunk, media_type="video/mp4", status_code=206,
                headers={
                    **headers,
                    "Content-Range": f"bytes {start}-{end}/{total_length}",
                    "Content-Length": str(len(chunk)),
                },
            )

    return Response(content=video_bytes, media_type="video/mp4", headers=headers)


@app.get("/analyses/{analysis_id}/video")
async def get_analysis_video(
    analysis_id: str, range_header: str | None = Header(None, alias="Range")
) -> Response:
    video_bytes = storage.get_video_bytes(analysis_id)
    if video_bytes is None:
        raise HTTPException(status_code=404, detail="Analyse introuvable.")
    return _video_response(
        video_bytes, f'attachment; filename="{analysis_id}_annotated.mp4"', range_header
    )


@app.get("/capsules/{capsule_id}/video")
async def get_capsule_video(
    capsule_id: str, range_header: str | None = Header(None, alias="Range")
) -> Response:
    """Vidéo générée d'un exercice du catalogue (voir capsule_build.py). L'id est
    d'abord cherché dans le catalogue : il n'est jamais utilisé tel quel pour
    construire un chemin (pas de traversée de répertoire possible)."""
    if capsule_id not in {exercise["id"] for exercise in exercises.load_catalog()}:
        raise HTTPException(status_code=404, detail="Exercice introuvable.")
    path = capsule_build.video_path(capsule_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Vidéo non générée pour cet exercice.")
    return _video_response(path.read_bytes(), f'inline; filename="{capsule_id}.mp4"', range_header)


@app.get("/analyses/{analysis_id}/pose3d")
async def get_analysis_pose3d(analysis_id: str) -> Response:
    pose3d_json = storage.get_pose3d_json(analysis_id)
    if pose3d_json is None:
        raise HTTPException(status_code=404, detail="Analyse introuvable.")
    return Response(content=pose3d_json, media_type="application/json")


@app.get("/analyses/{analysis_id}/frames.csv")
async def get_analysis_frames_csv(analysis_id: str) -> Response:
    csv_text = storage.frames_csv_text(analysis_id)
    if csv_text is None:
        raise HTTPException(status_code=404, detail="Analyse introuvable.")
    return Response(
        content=csv_text, media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{analysis_id}_frames.csv"'},
    )


def _annotate_program_videos(program: list[dict]) -> list[dict]:
    """Ajoute `video_available` à la capsule de chaque élément : la vidéo générée existe-t-elle ?"""
    for item in program:
        item["capsule"]["video_available"] = capsule_build.video_path(item["capsule"]["id"]).is_file()
    return program


@app.get("/analyses/{analysis_id}/recommendation")
async def get_analysis_recommendation(
    analysis_id: str, size: int = Query(DEFAULT_PROGRAM_SIZE, ge=1, le=MAX_PROGRAM_SIZE)
) -> dict:
    analysis = storage.get_analysis(analysis_id)
    frames = storage.get_frame_segments(analysis_id)
    if analysis is None or frames is None:
        raise HTTPException(status_code=404, detail="Analyse introuvable.")

    program = _annotate_program_videos(build_analysis_program(frames, analysis["load"], size))
    first = program[0] if program else None
    return {
        # `zone` et `capsule` : premier élément du programme, conservés pour les
        # clients qui ne lisent que la recommandation unique d'origine.
        "zone": first["zone"] if first else None,
        "capsule": first["capsule"] if first else None,
        "program": program,
        # Réservé à la correction du geste (Partie D de la spec), vide pour l'instant.
        "gesture_corrections": [],
        "load": analysis["load"],
    }


@app.get("/analyses/{analysis_id}/recurrence")
async def get_analysis_recurrence(analysis_id: str) -> dict:
    frames = storage.get_frame_angles(analysis_id)
    if frames is None:
        raise HTTPException(status_code=404, detail="Analyse introuvable.")
    return recurrence.compute_recurrence(frames, recurrence.load_thresholds())


class BilanCreate(BaseModel):
    label: str | None = None
    workday_hours: float = Field(default=9.0, gt=0, le=24)


class BilanDuplicate(BaseModel):
    label: str | None = None


class BilanAnalysisAttach(BaseModel):
    analysis_id: str
    activity_hours: float = Field(gt=0)
    representative: bool


def _get_bilan_or_404(bilan_id: str) -> dict:
    record = storage.get_bilan(bilan_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Bilan introuvable.")
    return record


@app.post("/bilans")
async def create_bilan(body: BilanCreate) -> dict:
    bilan_id = generate_run_id()
    storage.create_bilan(
        bilan_id=bilan_id, created_at=datetime.now(timezone.utc),
        label=body.label, workday_hours=body.workday_hours,
    )
    return _get_bilan_or_404(bilan_id)


@app.post("/bilans/{bilan_id}/duplicate")
async def duplicate_bilan(bilan_id: str, body: BilanDuplicate) -> dict:
    """Copie un bilan pour le reprendre avec une autre personne : libellé, durée de la journée et
    fiches d'activité. Les vidéos analysées ne sont pas copiées (ce sont celles de la personne
    d'origine), donc une fiche n'y reste pas liée."""
    original = _get_bilan_or_404(bilan_id)
    label = _clean_text(body.label)
    if label is None:
        label = f"Copie de {original['label']}" if original["label"] else "Copie de bilan"
    new_id = generate_run_id()
    storage.duplicate_bilan(
        source_id=bilan_id, new_id=new_id, created_at=datetime.now(timezone.utc), label=label,
        task_ids=[generate_run_id() for _ in original["tasks"]],
    )
    return _get_bilan_or_404(new_id)


class MetierBilanCreate(BaseModel):
    label: str | None = None


class MetierModelCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


def _library_entries() -> list[dict]:
    return [{**model, "origin": "library"} for model in metiers.load_library()]


def _custom_entries() -> list[dict]:
    return [
        {
            **model, "origin": "custom", "status": "draft", "source": "human",
            "validated_by": None, "validated_on": None,
        }
        for model in storage.list_metier_models()
    ]


def _get_metier_or_404(metier_id: str) -> dict:
    entry = next(
        (entry for entry in _library_entries() + _custom_entries() if entry["id"] == metier_id),
        None,
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Métier introuvable.")
    return entry


@app.get("/metiers")
async def list_metiers() -> list[dict]:
    """Modèles de métier : ceux de la bibliothèque (`origin: "library"`), puis ceux du praticien."""
    return _library_entries() + _custom_entries()


@app.post("/metiers/{metier_id}/bilan")
async def create_bilan_from_metier(metier_id: str, body: MetierBilanCreate) -> dict:
    """Crée un bilan prérempli avec les fiches d'activité types du métier. Le libellé sert
    d'ordinaire à nommer la personne."""
    model = _get_metier_or_404(metier_id)
    label = _clean_text(body.label) or model["title"]
    bilan_id = generate_run_id()
    now = datetime.now(timezone.utc)
    storage.create_bilan(
        bilan_id=bilan_id, created_at=now, label=label, workday_hours=model["workday_hours"],
    )
    for index, task in enumerate(model["tasks"]):
        storage.create_bilan_task(
            task_id=generate_run_id(), bilan_id=bilan_id,
            # Un décalage de quelques microsecondes garde l'ordre des fiches du modèle.
            created_at=now + timedelta(microseconds=index), task=metiers.task_to_stored(task),
        )
    return _get_bilan_or_404(bilan_id)


@app.post("/bilans/{bilan_id}/metier")
async def save_bilan_as_metier(bilan_id: str, body: MetierModelCreate) -> dict:
    """Enregistre les fiches d'activité du bilan comme modèle de métier réutilisable. Les vidéos
    et les mesures ne sont pas conservées : seulement la description des tâches."""
    record = _get_bilan_or_404(bilan_id)
    if not record["tasks"]:
        raise HTTPException(
            status_code=422, detail="Ajoutez au moins une fiche d'activité avant d'enregistrer un modèle."
        )
    tasks = []
    for task in record["tasks"]:
        entry = {
            "name": task["name"], "zones": task["zones"], "activity_hours": task["activity_hours"],
            "workstation": task["workstation"], "breaks": task["breaks"], "notes": task["notes"],
            "cycle_seconds": task["cycle_seconds"], "static_seconds": task["static_seconds"],
            "load_kg": task["load_kg"], "days_per_week": task["days_per_week"],
        }
        if task["zone_cycles"]:
            entry["zone_cycles"] = task["zone_cycles"]
        tasks.append(metiers.validate_task({k: v for k, v in entry.items() if v is not None}))
    model_id = f"perso-{generate_run_id()}"
    storage.create_metier_model(
        model_id=model_id, created_at=datetime.now(timezone.utc), title=body.title.strip(),
        description=_clean_text(body.description), workday_hours=record["workday_hours"],
        tasks=tasks,
    )
    return _get_metier_or_404(model_id)


@app.delete("/metiers/{metier_id}")
async def delete_metier(metier_id: str) -> dict:
    """Supprime un modèle du praticien. Ceux de la bibliothèque ne se suppriment pas."""
    if any(model["id"] == metier_id for model in _library_entries()):
        raise HTTPException(
            status_code=403, detail="Les métiers de la bibliothèque ne se suppriment pas."
        )
    if not storage.delete_metier_model(metier_id):
        raise HTTPException(status_code=404, detail="Métier introuvable.")
    return {"deleted": metier_id}


@app.get("/bilans")
async def list_bilans(archived: bool = False) -> list[dict]:
    """Bilans actifs ; `?archived=true` liste les archives."""
    return storage.list_bilans(archived=archived)


class FolderBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class FolderCreate(FolderBody):
    parent_id: str | None = None


class FolderMove(BaseModel):
    folder_id: str | None = None


class FolderReparent(BaseModel):
    parent_id: str | None = None


def _clean_folder_name(body: FolderBody) -> str:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Le nom du dossier est obligatoire.")
    return name


@app.get("/bilan-folders")
async def list_bilan_folders() -> list[dict]:
    """Dossiers de bilans (par exemple une entreprise), par ordre alphabétique."""
    return storage.list_bilan_folders()


@app.post("/bilan-folders")
async def create_bilan_folder(body: FolderCreate) -> dict:
    """Crée un dossier, à la racine ou dans `parent_id` (entreprise > service > poste)."""
    name = _clean_folder_name(body)
    folder_id = generate_run_id()
    try:
        storage.create_bilan_folder(
            folder_id=folder_id, created_at=datetime.now(timezone.utc), name=name,
            parent_id=body.parent_id,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Dossier parent introuvable.") from error
    except ValueError as error:
        raise HTTPException(
            status_code=409, detail="Un dossier porte déjà ce nom à cet endroit."
        ) from error
    return storage.get_bilan_folder(folder_id)


@app.put("/bilan-folders/{folder_id}")
async def rename_bilan_folder(folder_id: str, body: FolderBody) -> dict:
    name = _clean_folder_name(body)
    try:
        storage.rename_bilan_folder(folder_id=folder_id, name=name)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Dossier introuvable.") from error
    except ValueError as error:
        raise HTTPException(
            status_code=409, detail="Un dossier porte déjà ce nom à cet endroit."
        ) from error
    return storage.get_bilan_folder(folder_id)


@app.post("/bilan-folders/{folder_id}/move")
async def move_bilan_folder(folder_id: str, body: FolderReparent) -> dict:
    """Place le dossier (avec tout ce qu'il contient) dans un autre dossier ou à la racine."""
    try:
        storage.move_bilan_folder(folder_id=folder_id, parent_id=body.parent_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Dossier introuvable.") from error
    except storage.FolderCycleError as error:
        raise HTTPException(
            status_code=422,
            detail="Un dossier ne peut pas être placé dans lui-même ni dans l'un de ses sous-dossiers.",
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=409, detail="Un dossier porte déjà ce nom à cet endroit."
        ) from error
    return storage.get_bilan_folder(folder_id)


@app.delete("/bilan-folders/{folder_id}")
async def delete_bilan_folder(folder_id: str) -> dict:
    """Supprime le dossier seulement : ses sous-dossiers et ses bilans montent d'un niveau."""
    try:
        deleted = storage.delete_bilan_folder(folder_id)
    except ValueError as error:
        raise HTTPException(
            status_code=409,
            detail="Un sous-dossier porte le même nom qu'un dossier du niveau au-dessus : renommez-le d'abord.",
        ) from error
    if not deleted:
        raise HTTPException(status_code=404, detail="Dossier introuvable.")
    return {"deleted": folder_id}


@app.post("/bilans/{bilan_id}/folder")
async def move_bilan_to_folder(bilan_id: str, body: FolderMove) -> dict:
    """Range le bilan dans un dossier ; `folder_id: null` le sort de son dossier."""
    _get_bilan_or_404(bilan_id)
    try:
        storage.set_bilan_folder(bilan_id=bilan_id, folder_id=body.folder_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Dossier introuvable.") from error
    return _get_bilan_or_404(bilan_id)


@app.post("/bilans/{bilan_id}/archive")
async def archive_bilan(bilan_id: str) -> dict:
    """Range le bilan dans les archives : il quitte la liste, rien n'est perdu."""
    _get_bilan_or_404(bilan_id)
    storage.set_bilan_archived(bilan_id=bilan_id, archived_at=datetime.now(timezone.utc))
    return _get_bilan_or_404(bilan_id)


@app.post("/bilans/{bilan_id}/unarchive")
async def unarchive_bilan(bilan_id: str) -> dict:
    """Sort le bilan des archives."""
    _get_bilan_or_404(bilan_id)
    storage.set_bilan_archived(bilan_id=bilan_id, archived_at=None)
    return _get_bilan_or_404(bilan_id)


@app.delete("/bilans/{bilan_id}")
async def delete_bilan(bilan_id: str) -> dict:
    """Supprime définitivement le bilan et ses fiches ; les vidéos analysées sont conservées."""
    if not storage.delete_bilan(bilan_id):
        raise HTTPException(status_code=404, detail="Bilan introuvable.")
    return {"deleted": bilan_id}


@app.get("/bilans/{bilan_id}")
async def get_bilan(bilan_id: str) -> dict:
    return _get_bilan_or_404(bilan_id)


@app.post("/bilans/{bilan_id}/analyses")
async def attach_analysis_to_bilan(bilan_id: str, body: BilanAnalysisAttach) -> dict:
    record = _get_bilan_or_404(bilan_id)
    if storage.get_analysis(body.analysis_id) is None:
        raise HTTPException(status_code=404, detail="Analyse introuvable.")
    if any(item["analysis_id"] == body.analysis_id for item in record["items"]):
        raise HTTPException(status_code=409, detail="Analyse déjà rattachée à ce bilan.")

    documented_hours = sum(item["activity_hours"] for item in record["items"]) + sum(
        task["activity_hours"] for task in record["tasks"] if task["analysis_id"] is None
    )
    if documented_hours + body.activity_hours > record["workday_hours"]:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Les activités documentées dépasseraient la journée de "
                f"{record['workday_hours']} h."
            ),
        )

    storage.attach_analysis(
        bilan_id=bilan_id, analysis_id=body.analysis_id,
        activity_hours=body.activity_hours, representative=body.representative,
    )
    return _get_bilan_or_404(bilan_id)


ZONE_NAMES = Literal["neck", "trunk", "upper_arm", "lower_arm", "hand", "foot"]


class TimeSlot(BaseModel):
    start: str
    end: str


class BilanTaskBody(BaseModel):
    name: str
    zones: list[ZONE_NAMES] = Field(min_length=1)
    activity_hours: float | None = Field(default=None, gt=0, le=24)
    time_slots: list[TimeSlot] | None = None
    days_per_week: float | None = Field(default=None, gt=0, le=7)
    # Fréquence propre à chaque zone ; `cycles_per_minute` : raccourci appliqué aux
    # zones cochées qui n'ont pas de valeur propre.
    zone_cycles_per_minute: dict[ZONE_NAMES, float] | None = None
    cycles_per_minute: float | None = Field(default=None, ge=0)
    cycle_seconds: float | None = Field(default=None, gt=0)
    static_seconds: float | None = Field(default=None, ge=0)
    load_kg: float | None = Field(default=None, ge=0)
    analysis_id: str | None = None
    source: Literal["practitioner", "patient"] = "practitioner"
    notes: str | None = None
    workstation: str | None = Field(default=None, max_length=200)
    breaks: str | None = Field(default=None, max_length=200)


def _clean_text(text: str | None) -> str | None:
    return text.strip() if text and text.strip() else None


def _validated_task(record: dict, body: BilanTaskBody, *, exclude_task_id: str | None) -> dict:
    """Valide une fiche et renvoie les champs à stocker. HTTPException 422 sinon."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Le nom de la tâche est obligatoire.")
    zones = list(dict.fromkeys(body.zones))

    slots = [slot.model_dump() for slot in body.time_slots] if body.time_slots else None
    linked_item = next(
        (item for item in record["items"] if item["analysis_id"] == body.analysis_id), None
    )
    if body.analysis_id is not None and linked_item is None:
        raise HTTPException(
            status_code=422, detail="L'analyse à compléter n'est pas rattachée à ce bilan."
        )
    try:
        if slots is not None:
            hours = bilan.slots_hours(slots)
        elif body.activity_hours is not None:
            hours = body.activity_hours
        elif linked_item is not None:
            hours = linked_item["activity_hours"]
        else:
            raise ValueError("Indiquez la durée de la tâche ou ses plages horaires.")
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    # Une fiche liée à une vidéo reprend sa durée : elle n'ajoute rien à la journée.
    if linked_item is None:
        documented = sum(item["activity_hours"] for item in record["items"]) + sum(
            task["activity_hours"] for task in record["tasks"]
            if task["id"] != exclude_task_id and task["analysis_id"] is None
        )
        if documented + hours > record["workday_hours"] + 1e-9:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Les activités documentées dépasseraient la journée de "
                    f"{record['workday_hours']} h."
                ),
            )
    zone_cycles = {}
    for zone, value in (body.zone_cycles_per_minute or {}).items():
        if zone not in zones:
            raise HTTPException(
                status_code=422,
                detail="Une fréquence est donnée pour une zone qui n'est pas cochée.",
            )
        if value < 0:
            raise HTTPException(status_code=422, detail="Les répétitions doivent être positives.")
        zone_cycles[zone] = value
    if body.cycles_per_minute is not None:
        for zone in zones:
            zone_cycles.setdefault(zone, body.cycles_per_minute)

    return {
        "name": name, "zones": zones, "activity_hours": hours, "time_slots": slots,
        "days_per_week": body.days_per_week, "zone_cycles": zone_cycles,
        "workstation": _clean_text(body.workstation), "breaks": _clean_text(body.breaks),
        "cycle_seconds": body.cycle_seconds, "static_seconds": body.static_seconds,
        "load_kg": body.load_kg, "analysis_id": body.analysis_id, "source": body.source,
        "notes": _clean_text(body.notes),
    }


@app.post("/bilans/{bilan_id}/tasks")
async def create_bilan_task(bilan_id: str, body: BilanTaskBody) -> dict:
    record = _get_bilan_or_404(bilan_id)
    task = _validated_task(record, body, exclude_task_id=None)
    storage.create_bilan_task(
        task_id=generate_run_id(), bilan_id=bilan_id,
        created_at=datetime.now(timezone.utc), task=task,
    )
    return _get_bilan_or_404(bilan_id)


@app.put("/bilans/{bilan_id}/tasks/{task_id}")
async def update_bilan_task(bilan_id: str, task_id: str, body: BilanTaskBody) -> dict:
    record = _get_bilan_or_404(bilan_id)
    if not any(task["id"] == task_id for task in record["tasks"]):
        raise HTTPException(status_code=404, detail="Tâche introuvable.")
    task = _validated_task(record, body, exclude_task_id=task_id)
    storage.update_bilan_task(task_id=task_id, bilan_id=bilan_id, task=task)
    return _get_bilan_or_404(bilan_id)


@app.delete("/bilans/{bilan_id}/tasks/{task_id}")
async def delete_bilan_task(bilan_id: str, task_id: str) -> dict:
    record = _get_bilan_or_404(bilan_id)
    if not any(task["id"] == task_id for task in record["tasks"]):
        raise HTTPException(status_code=404, detail="Tâche introuvable.")
    storage.delete_bilan_task(task_id=task_id, bilan_id=bilan_id)
    return _get_bilan_or_404(bilan_id)


def _build_bilan_report(record: dict) -> dict:
    thresholds = recurrence.load_thresholds()
    items = []
    for item in record["items"]:
        frames = storage.get_frame_angles(item["analysis_id"])
        items.append({
            **item,
            "recurrence": recurrence.compute_recurrence(frames or [], thresholds),
        })
    return bilan.project_bilan(record["workday_hours"], items, record["tasks"])


@app.get("/bilans/{bilan_id}/recurrence")
async def get_bilan_recurrence(bilan_id: str) -> dict:
    return _build_bilan_report(_get_bilan_or_404(bilan_id))


def _program_catalog() -> list[dict]:
    """Exercices que le praticien peut ajouter à la main (hors exercices allongés)."""
    return [
        {"id": c.id, "zone": c.zone, "title": c.title, "position": c.position}
        for c in CAPSULES if c.position != "lying"
    ]


@app.get("/bilans/{bilan_id}/program")
async def get_bilan_program(
    bilan_id: str, size: int | None = Query(None, ge=1, le=MAX_PROGRAM_SIZE)
) -> dict:
    """Programme d'étirements du bilan. Nombre d'exercices : `?size=`, sinon le réglage enregistré,
    sinon 5. Si le praticien a choisi ses exercices, c'est sa sélection qui est renvoyée."""
    record = _get_bilan_or_404(bilan_id)
    settings = storage.get_program_settings(bilan_id)
    size = size or settings["size"] or DEFAULT_PROGRAM_SIZE
    report = _build_bilan_report(record)
    position = bilan.preferred_position(record["tasks"])
    selection = settings["exercise_ids"]
    if selection is None:
        program = build_bilan_program(report, position, record["tasks"], size)
    else:
        full = build_bilan_program(report, position, record["tasks"], 200)
        program = select_program(selection, full, record["tasks"])
    warnings = list(report["warnings"])
    if any(item["basis"] == "declared" for item in program):
        warnings.append(
            "Une partie du programme vient des tâches saisies : sans vidéo, aucune posture n'est "
            "mesurée. Il se précise avec une analyse vidéo du poste."
        )
    return {
        "program": _annotate_program_videos(program),
        "size": size,
        "selection": selection,
        "available": _program_catalog(),
        "position": position,
        "position_note": (
            "Poste de travail assis (d'après les tâches saisies) : exercices proposés assis "
            "quand ils existent."
            if position == "seated" else None
        ),
        # Réservé à la correction du geste (Partie D de la spec), vide pour l'instant.
        "gesture_corrections": [],
        "warnings": warnings,
    }


class LoadUpdate(BaseModel):
    kind: Literal["none", "exact", "range"]
    kg: float | None = None
    kg_min: float | None = None
    kg_max: float | None = None


def _score_summary(summary: dict) -> dict:
    return {"max_score": summary["max_score"], "average_score": summary["average_score"]}


@app.put("/analyses/{analysis_id}/load")
async def update_analysis_load(analysis_id: str, body: LoadUpdate) -> dict:
    """Saisie du poids manipulé après l'analyse (la vidéo ne peut pas le
    deviner). Recalcule les scores à partir des sous-scores déjà persistés,
    sans relancer la pose. Une fourchette est calculée aux deux bornes : les
    valeurs stockées sont celles du cas défavorable (borne haute), l'intervalle
    est conservé dans load.score_range."""
    frames = storage.get_frame_scores(analysis_id)
    if frames is None:
        raise HTTPException(status_code=404, detail="Analyse introuvable.")

    try:
        load = parse_load(body.kind, body.kg, body.kg_min, body.kg_max)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    low_kg, high_kg = bounds(load)
    high_summary = summarize_for_load(frames, high_kg)
    score_range = None
    if low_kg != high_kg:
        score_range = {
            "low": _score_summary(summarize_for_load(frames, low_kg)),
            "high": _score_summary(high_summary),
        }

    try:
        storage.update_load(
            analysis_id,
            load={"kind": load.kind, "kg": load.kg, "kg_min": load.kg_min, "kg_max": load.kg_max},
            effective_load_kg=high_kg,
            frame_scores=rescore_frames(frames, high_kg),
            summary=high_summary,
            score_range=score_range,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Analyse introuvable.") from error

    return storage.get_analysis(analysis_id)


_EXERCISE_SUMMARY_KEYS = (
    "id", "zone", "title", "description", "status", "source", "view", "target_segments",
    "duration_seconds",
)


@app.get("/exercises")
async def list_exercises() -> list[dict]:
    return [
        {
            **{key: exercise[key] for key in _EXERCISE_SUMMARY_KEYS},
            "position": exercise.get("position", exercises.DEFAULT_POSITION),
        }
        for exercise in exercises.load_catalog()
    ]


@app.get("/exercises/{exercise_id}")
async def get_exercise(exercise_id: str) -> dict:
    # L'id n'est jamais utilisé pour construire un chemin : on le cherche dans le
    # catalogue déjà chargé (pas de traversée de répertoire possible).
    for exercise in exercises.load_catalog():
        if exercise["id"] == exercise_id:
            return exercise
    raise HTTPException(status_code=404, detail="Exercice introuvable.")


@app.get("/version")
async def get_version() -> dict:
    return {"version": version.get_version()}


@app.get("/library")
async def get_library() -> dict:
    try:
        return library.load_library()
    except ValueError as error:
        raise HTTPException(status_code=500, detail=f"Bibliothèque invalide : {error}") from error


_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_SHARE_ITEMS = 30


class LibraryShareItem(BaseModel):
    exercise_id: str
    note: str | None = Field(default=None, max_length=500)


class LibraryShareCreate(BaseModel):
    recipient_email: str = Field(max_length=254)
    practitioner_name: str | None = Field(default=None, max_length=120)
    message: str | None = Field(default=None, max_length=2000)
    items: list[LibraryShareItem] = Field(min_length=1, max_length=MAX_SHARE_ITEMS)


def _blank_to_none(value: str | None) -> str | None:
    return value.strip() or None if value is not None else None


@app.post("/library/shares")
async def create_library_share(body: LibraryShareCreate) -> dict:
    recipient = body.recipient_email.strip()
    if not _EMAIL_PATTERN.match(recipient):
        raise HTTPException(status_code=422, detail="Adresse email invalide.")

    catalog = {exercise["id"]: exercise for exercise in exercises.load_catalog()}
    unknown = [item.exercise_id for item in body.items if item.exercise_id not in catalog]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Exercice introuvable : {unknown[0]}.")
    if len({item.exercise_id for item in body.items}) != len(body.items):
        raise HTTPException(status_code=422, detail="Exercice en double dans l'envoi.")

    practitioner_name = _blank_to_none(body.practitioner_name)
    message = _blank_to_none(body.message)
    items = [
        {"exercise_id": item.exercise_id, "note": _blank_to_none(item.note)}
        for item in body.items
    ]
    token = secrets.token_urlsafe(16)
    share_path = f"/bibliotheque/envoi/{token}"
    outgoing = mailer.build_share_message(
        to=recipient,
        share_url=f"{mailer.public_web_url()}{share_path}",
        practitioner_name=practitioner_name,
        message=message,
        exercise_titles=[catalog[item["exercise_id"]]["title"] for item in items],
    )

    try:
        service = mailer.get_mailer()
    except mailer.MailerError:
        email_status = "failed"
    else:
        try:
            await run_in_threadpool(service.send, outgoing)
            email_status = "sent"
        except mailer.MailerError:
            email_status = "not_configured" if isinstance(service, mailer.NullMailer) else "failed"

    storage.save_library_share(
        token=token,
        created_at=datetime.now(timezone.utc),
        recipient_email=recipient,
        practitioner_name=practitioner_name,
        message=message,
        items=items,
        email_status=email_status,
    )
    return {"token": token, "share_path": share_path, "email_status": email_status}


@app.get("/library/shares/{token}")
async def get_library_share(token: str) -> dict:
    share = storage.get_library_share(token)
    if share is None:
        raise HTTPException(status_code=404, detail="Envoi introuvable.")
    catalog = {exercise["id"]: exercise for exercise in exercises.load_catalog()}
    return {
        "created_at": share["created_at"],
        "practitioner_name": share["practitioner_name"],
        "message": share["message"],
        "items": [
            {"exercise": catalog[item["exercise_id"]], "note": item["note"]}
            for item in share["items"]
            if item["exercise_id"] in catalog
        ],
    }


class ProgramSettingsBody(BaseModel):
    size: int | None = Field(default=None, ge=1, le=MAX_PROGRAM_SIZE)
    # None : programme automatique ; une liste : exercices choisis par le praticien, dans l'ordre.
    exercise_ids: list[str] | None = Field(default=None, max_length=MAX_PROGRAM_SIZE * 2)


@app.put("/bilans/{bilan_id}/program")
async def put_bilan_program_settings(bilan_id: str, body: ProgramSettingsBody) -> dict:
    """Enregistre le nombre d'exercices et, éventuellement, la sélection du praticien."""
    _get_bilan_or_404(bilan_id)
    known = {capsule.id for capsule in CAPSULES}
    unknown = [i for i in body.exercise_ids or [] if i not in known]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Exercices inconnus : {', '.join(unknown)}")
    storage.set_program_settings(
        bilan_id=bilan_id, size=body.size,
        exercise_ids=list(dict.fromkeys(body.exercise_ids)) if body.exercise_ids is not None else None,
    )
    return await get_bilan_program(bilan_id, size=None)
