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
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import cv2
from fastapi import FastAPI, File, Form, Header, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from tms_vision import bilan, recurrence, storage
from tms_vision.load import bounds, parse_load
from tms_vision.program import build_analysis_program, build_bilan_program
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

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    # GET est volontairement absent : une requête GET "simple" (sans en-tête
    # personnalisé) ne déclenche pas de preflight CORS, donc pas besoin de la
    # lister ici -- ça vaut pour les routes GET /analyses/... (vidéo/CSV/
    # pose3D) comme ça valait pour l'ancienne route GET /outputs/{filename}.
    allow_methods=["POST", "PUT"],
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


@app.get("/analyses/{analysis_id}/video")
async def get_analysis_video(
    analysis_id: str, range_header: str | None = Header(None, alias="Range")
) -> Response:
    """Sert la vidéo annotée avec support des requêtes HTTP Range (RFC 7233,
    un seul intervalle) -- nécessaire pour que <video> fonctionne de façon
    fiable sur iOS Safari (voir skill iphone-tunnel-test), qui s'appuie sur
    Range pour le seek et le pré-chargement progressif. L'ancienne route
    GET /outputs/{filename} l'avait gratuitement via FileResponse ; ce n'est
    plus le cas ici puisque le contenu vient de DuckDB (bytes en mémoire),
    d'où ce handling explicite."""
    video_bytes = storage.get_video_bytes(analysis_id)
    if video_bytes is None:
        raise HTTPException(status_code=404, detail="Analyse introuvable.")

    total_length = len(video_bytes)
    headers = {
        "Content-Disposition": f'attachment; filename="{analysis_id}_annotated.mp4"',
        "Accept-Ranges": "bytes",
    }

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


@app.get("/analyses/{analysis_id}/recommendation")
async def get_analysis_recommendation(analysis_id: str) -> dict:
    analysis = storage.get_analysis(analysis_id)
    frames = storage.get_frame_segments(analysis_id)
    if analysis is None or frames is None:
        raise HTTPException(status_code=404, detail="Analyse introuvable.")

    program = build_analysis_program(frames, analysis["load"])
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


@app.get("/bilans")
async def list_bilans() -> list[dict]:
    return storage.list_bilans()


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

    documented_hours = sum(item["activity_hours"] for item in record["items"])
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


def _build_bilan_report(record: dict) -> dict:
    thresholds = recurrence.load_thresholds()
    items = []
    for item in record["items"]:
        frames = storage.get_frame_angles(item["analysis_id"])
        items.append({
            **item,
            "recurrence": recurrence.compute_recurrence(frames or [], thresholds),
        })
    return bilan.project_bilan(record["workday_hours"], items)


@app.get("/bilans/{bilan_id}/recurrence")
async def get_bilan_recurrence(bilan_id: str) -> dict:
    return _build_bilan_report(_get_bilan_or_404(bilan_id))


@app.get("/bilans/{bilan_id}/program")
async def get_bilan_program(bilan_id: str) -> dict:
    report = _build_bilan_report(_get_bilan_or_404(bilan_id))
    return {
        "program": build_bilan_program(report),
        # Réservé à la correction du geste (Partie D de la spec), vide pour l'instant.
        "gesture_corrections": [],
        "warnings": report["warnings"],
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
