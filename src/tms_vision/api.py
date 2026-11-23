"""API FastAPI : expose le pipeline Phase 1 (tms_vision.pipeline) pour la
capture web. Reçoit un clip vidéo (enregistré dans le navigateur en un seul
POST /analyses, ou importé et envoyé par chunks via POST /uploads + PUT
.../chunks/{index} + POST .../complete), lance l'analyse RULA existante,
persiste le résultat en DuckDB (tms_vision.storage) et renvoie le résumé +
les liens vers les ressources produites (voir
docs/superpowers/specs/2026-09-14-web-capture-fastapi-design.md,
docs/superpowers/specs/2026-09-15-web-upload-chunked-design.md et
docs/superpowers/specs/2026-09-22-duckdb-analysis-storage-design.md)."""
import dataclasses
import json
import os
import re
import secrets
import shutil
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import cv2
from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from tms_vision import (
    accounts, assistant, auth_api, bilan, capsule_build, exercises, library, mailer, metiers, recurrence, self_update, storage,
    sheets, updates, user_email, validation, version,
)
from tms_vision.load import bounds, parse_load
from tms_vision.capsules import (
    CAPSULES, DEFAULT_PROGRAM_SIZE, MAX_PROGRAM_SIZE, capsule_from_exercise,
)
from tms_vision.program import (
    ZONE_LABELS, build_analysis_program, build_bilan_program, select_program,
)
from tms_vision.rescore import rescore_frames, summarize_for_load
from tms_vision.pipeline import analyze_video, generate_run_id
from tms_vision.pose_models import PoseModelError, PoseOptions, available_models, wholebody_setup
from tms_vision.pose3d_export import build_pose3d_payload

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Garde-fou de durée : analyze_video() lit un fichier image par image (deux passes, voir pipeline.py),
# donc la mémoire ne dépend pas de sa durée, mais le temps de calcul oui. Au-delà, le praticien est
# invité à découper la vidéo (le protocole vise 30 secondes à 3 minutes).
MAX_VIDEO_SECONDS = 10 * 60

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
app.include_router(auth_api.router)
app.include_router(auth_api.admin_router)
app.include_router(auth_api.me_email_router)
# Ajouté avant CORS : CORS reste le plus extérieur, les réponses 401 portent donc ses en-têtes.
app.add_middleware(auth_api.AuthMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    # Le cookie de session accompagne les requêtes du site (origines listées, jamais « * »).
    allow_credentials=True,
    # GET est volontairement absent : une requête GET "simple" (sans en-tête
    # personnalisé) ne déclenche pas de preflight CORS, donc pas besoin de la
    # lister ici -- ça vaut pour les routes GET /analyses/... (vidéo/CSV/
    # pose3D) comme ça valait pour l'ancienne route GET /outputs/{filename}.
    # DELETE : suppression d'une fiche d'activité et d'un modèle de métier depuis le site.
    # PATCH : modification d'un compte (rôles, activation) depuis la page Administration.
    allow_methods=["POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)


def _reject_if_too_long(video_path: Path) -> None:
    capture = cv2.VideoCapture(str(video_path))
    try:
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    finally:
        capture.release()

    if frame_count / fps > MAX_VIDEO_SECONDS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Vidéo trop longue pour être analysée (plus de {MAX_VIDEO_SECONDS // 60} minutes). "
                "Découpez-la : une séquence représentative de 30 secondes à 3 minutes suffit."
            ),
        )


async def _analyze_and_build_response(
    video_path: Path,
    side: str,
    load_kg: float,
    wrist_twist: str,
    worker_label: str | None,
    poste_label: str | None,
    pose_options: PoseOptions | None = None,
) -> dict:
    """Appelle analyze_video sur un fichier déjà sur disque, persiste le
    résultat en DuckDB et construit la réponse JSON standard. Partagé par
    create_analysis (upload direct) et complete_upload (upload par chunks) :
    les deux finissent par produire un seul fichier vidéo local, traité de
    façon identique à partir de ce point."""
    _reject_if_too_long(video_path)
    try:
        result = await run_in_threadpool(
            analyze_video, source=str(video_path), side=side, load_kg=load_kg,
            wrist_twist=wrist_twist, pose_options=pose_options,
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
        pose_model=result.pose_options.pose_model, pose_options=result.pose_options.to_json(),
        keypoint_count=result.keypoint_count,
        hands_metrics=json.dumps(result.hands_metrics) if result.hands_metrics is not None else None,
        custom_metrics=json.dumps(result.custom_metrics, ensure_ascii=False) if result.custom_metrics is not None else None,
        detection_quality=json.dumps(result.detection_quality),
        keypoint_frames=[p.to_dict() for p in result.keypoint_frames or []],
    )

    return {
        "analysis_id": analysis_id,
        "summary": result.summary,
        "annotated_video_url": f"/analyses/{analysis_id}/video",
        "csv_url": f"/analyses/{analysis_id}/frames.csv",
        "pose3d_url": f"/analyses/{analysis_id}/pose3d",
        "side": side,
        "pose_model": result.pose_options.pose_model,
        "keypoint_count": result.keypoint_count,
        "keypoints_url": f"/analyses/{analysis_id}/keypoints",
        "hands_metrics": result.hands_metrics,
        "custom_metrics": result.custom_metrics,
        "detection_quality": result.detection_quality,
        "pose_options": asdict(result.pose_options),
    }


def _pose_options_or_422(
    pose_model: str, enable_hands: bool, enable_wholebody: bool, enable_feet: bool,
    enable_face: bool, custom_points: bool, custom_points_json: str | None = None,
) -> PoseOptions:
    """Valide les options de modèle avant d'accepter la vidéo : une erreur claire (422) plutôt
    qu'une analyse qui échoue ou ignore l'option. `custom_points_json` : points placés par
    l'utilisateur, {"reference_time_seconds": 1.5, "points": [{"name": "outil", "x": 0.4, "y": 0.6}]}."""
    try:
        custom_spec = json.loads(custom_points_json) if custom_points_json else None
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=422, detail="Points personnalisés : JSON invalide.") from error
    try:
        return PoseOptions(
            pose_model=pose_model, enable_hands=enable_hands, enable_wholebody=enable_wholebody,
            enable_feet=enable_feet, enable_face=enable_face, custom_points=custom_points,
            custom_spec=custom_spec,
        ).validate()
    except PoseModelError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/pose-models")
async def list_pose_models() -> list[dict]:
    """Modèles de pose proposés par le sélecteur de l'interface."""
    return available_models()


@app.get("/pose-models/wholebody")
async def get_wholebody_status() -> dict:
    """État du modèle whole-body : paquets présents, poids téléchargés, mode, téléchargement en cours."""
    return wholebody_setup.status()


class WholebodySettings(BaseModel):
    mode: Literal["performance", "balanced", "lightweight"]


@app.put("/pose-models/wholebody")
async def put_wholebody_settings(body: WholebodySettings) -> dict:
    """Choix de la vitesse du modèle whole-body (précision maximale, équilibré, rapide)."""
    wholebody_setup.set_mode(body.mode)
    return wholebody_setup.status()


@app.post("/pose-models/wholebody/install")
async def install_wholebody() -> dict:
    """Télécharge les poids du modèle whole-body en arrière-plan (une seule fois). Se suit avec
    GET /pose-models/wholebody."""
    if not wholebody_setup.dependencies_available():
        raise HTTPException(
            status_code=422,
            detail="Le modèle whole-body n'est pas installé sur cette installation (voir docs/POSE-MODELES.md).",
        )
    if not wholebody_setup.weights_ready():
        wholebody_setup.start_download()
    return wholebody_setup.status()


@app.post("/analyses")
async def create_analysis(
    file: UploadFile = File(...),
    side: Literal["left", "right"] = Form(...),
    load_kg: float = Form(0.0, ge=0),
    wrist_twist: Literal["normal", "extreme"] = Form(...),
    worker_label: str | None = Form(None, max_length=200),
    poste_label: str | None = Form(None, max_length=200),
    pose_model: str = Form("mediapipe_pose_33", max_length=60),
    enable_hands: bool = Form(False),
    enable_wholebody: bool = Form(False),
    enable_feet: bool = Form(False),
    enable_face: bool = Form(False),
    custom_points: bool = Form(False),
    custom_points_json: str | None = Form(None, max_length=20000),
) -> dict:
    pose_options = _pose_options_or_422(
        pose_model, enable_hands, enable_wholebody, enable_feet, enable_face, custom_points,
        custom_points_json,
    )
    suffix = Path(file.filename or "").suffix or ".webm"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    upload_path = Path(tmp.name)
    try:
        with tmp:
            shutil.copyfileobj(file.file, tmp)
        return await _analyze_and_build_response(
            upload_path, side, load_kg, wrist_twist, worker_label, poste_label, pose_options
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
    pose_model: str = Form("mediapipe_pose_33", max_length=60),
    enable_hands: bool = Form(False),
    enable_wholebody: bool = Form(False),
    enable_feet: bool = Form(False),
    enable_face: bool = Form(False),
    custom_points: bool = Form(False),
    custom_points_json: str | None = Form(None, max_length=20000),
) -> dict:
    pose_options = _pose_options_or_422(
        pose_model, enable_hands, enable_wholebody, enable_feet, enable_face, custom_points,
        custom_points_json,
    )
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
            upload_path, side, load_kg, wrist_twist, worker_label, poste_label, pose_options
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


@app.get("/analyses/{analysis_id}/keypoints")
async def get_analysis_keypoints(analysis_id: str) -> dict:
    """Export JSON des points des modèles complémentaires (mains...) au format normalisé."""
    frames = storage.get_keypoints(analysis_id)
    if frames is None:
        raise HTTPException(status_code=404, detail="Analyse introuvable.")
    return {"analysis_id": analysis_id, "frames": frames}


@app.get("/analyses/{analysis_id}/frames.csv")
async def get_analysis_frames_csv(analysis_id: str) -> Response:
    csv_text = storage.frames_csv_text(analysis_id)
    if csv_text is None:
        raise HTTPException(status_code=404, detail="Analyse introuvable.")
    return Response(
        content=csv_text, media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{analysis_id}_frames.csv"'},
    )


def _annotate_program_videos(
    program: list[dict], osteo_id: str | None = None, user: dict | None = None
) -> list[dict]:
    """Ajoute à la capsule de chaque élément `video_available` (la vidéo générée existe-t-elle ?) et
    `validation` : étiquette « créé par / validé par » de la version courante. `can_validate` : le
    bouton « Valider » n'est visible que pour l'ostéopathe choisi sur le bilan (ou, sans choix, pour
    tout ostéopathe), tant qu'il n'a pas déjà validé la fiche ; l'API refuse de toute façon les
    autres comptes."""
    by_id = {
        exercise["id"]: exercise
        for exercise in validation.load_effective_catalog(include_archived=True)
    }
    labels = validation.labels_for(
        [by_id[item["capsule"]["id"]] for item in program if item["capsule"]["id"] in by_id],
        osteo_id,
    )
    may_validate = validation.is_osteopath(user) and (osteo_id is None or user["id"] == osteo_id)
    for item in program:
        capsule = item["capsule"]
        capsule["video_available"] = capsule_build.video_path(capsule["id"]).is_file()
        label = labels.get(capsule["id"])
        if label is not None:
            already = user is not None and user["id"] in label["validator_ids"]
            capsule["validation"] = {
                **_public_label(label), "can_validate": may_validate and not already,
            }
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


class MetierModelBody(BaseModel):
    """Modèle de métier saisi au formulaire : les fiches types sont revalidées par le serveur."""

    title: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    workday_hours: float = Field(gt=0, le=metiers.MAX_WORKDAY_HOURS)
    tasks: list[dict] = Field(min_length=1, max_length=50)


def _clean_metier_body(body: MetierModelBody) -> tuple[str, str | None, float, list[dict]]:
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Le titre est obligatoire.")
    try:
        tasks = [metiers.validate_task(task, f"fiche {i + 1}") for i, task in enumerate(body.tasks)]
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    total = sum(task["activity_hours"] for task in tasks)
    if total > body.workday_hours + 1e-9:
        raise HTTPException(
            status_code=422,
            detail=f"{total} h de tâches dépassent la journée de {body.workday_hours} h.",
        )
    return title, _clean_text(body.description), body.workday_hours, tasks


@app.post("/metiers")
async def create_metier(body: MetierModelBody) -> dict:
    """Crée un modèle de métier directement, sans passer par un bilan."""
    title, description, workday_hours, tasks = _clean_metier_body(body)
    model_id = f"perso-{generate_run_id()}"
    storage.create_metier_model(
        model_id=model_id, created_at=datetime.now(timezone.utc), title=title,
        description=description, workday_hours=workday_hours, tasks=tasks,
    )
    return _get_metier_or_404(model_id)


@app.put("/metiers/{metier_id}")
async def update_metier(metier_id: str, body: MetierModelBody) -> dict:
    """Modifie un modèle du praticien. Ceux de la bibliothèque ne se modifient pas."""
    if any(model["id"] == metier_id for model in _library_entries()):
        raise HTTPException(
            status_code=403, detail="Les métiers de la bibliothèque ne se modifient pas."
        )
    title, description, workday_hours, tasks = _clean_metier_body(body)
    if not storage.update_metier_model(
        metier_id, title=title, description=description, workday_hours=workday_hours, tasks=tasks,
    ):
        raise HTTPException(status_code=404, detail="Métier introuvable.")
    return _get_metier_or_404(metier_id)


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


def _db_capsules(*, validated_only: bool) -> list:
    """Capsules des fiches d'ostéopathes en base (copies et créations, hors archivées). Dans les
    programmes automatiques, seules celles validées par quelqu'un entrent ; pour l'ajout à la main,
    toutes."""
    from_db = [
        exercise for exercise in validation.load_effective_catalog()
        if exercise["id"] not in _file_ids()
    ]
    if validated_only and from_db:
        labels = validation.labels_for(from_db)
        from_db = [e for e in from_db if labels[e["id"]]["validated_by"]]
    return [capsule_from_exercise(exercise) for exercise in from_db]


def _file_ids() -> set[str]:
    return {capsule.id for capsule in CAPSULES}


def _program_catalog() -> list[dict]:
    """Exercices que le praticien peut ajouter à la main (hors exercices allongés)."""
    return [
        {"id": c.id, "zone": c.zone, "title": c.title, "position": c.position}
        for c in [*CAPSULES, *_db_capsules(validated_only=False)] if c.position != "lying"
    ]


def _osteo_candidate_filter(osteo_id: str, uncovered_zones: set[str]):
    """Filtre du programme pour l'ostéopathe X : seuls les exercices dont la version courante est
    validée par X sont proposés. Un exercice validé par un confrère ne passe pas sous le nom de X :
    X doit le revalider (page Relecture) pour engager sa responsabilité. Les zones qui n'ont aucun
    exercice validé par X sont ajoutées à `uncovered_zones`, pour être signalées au praticien."""
    by_id = {exercise["id"]: exercise for exercise in validation.load_effective_catalog()}
    labels = validation.labels_for(list(by_id.values()), osteo_id)

    def keep(capsules: list) -> list:
        validated = [
            capsule for capsule in capsules
            if labels.get(capsule.id, {}).get("validated_by_selected")
        ]
        if capsules and not validated:
            uncovered_zones.add(capsules[0].zone)
        return validated

    return keep


@app.get("/bilans/{bilan_id}/program")
async def get_bilan_program(
    bilan_id: str, request: Request, size: int | None = Query(None, ge=1, le=MAX_PROGRAM_SIZE)
) -> dict:
    """Programme d'étirements du bilan. Nombre d'exercices : `?size=`, sinon le réglage enregistré,
    sinon 5. Si le praticien a choisi ses exercices, c'est sa sélection qui est renvoyée."""
    record = _get_bilan_or_404(bilan_id)
    settings = storage.get_program_settings(bilan_id)
    size = size or settings["size"] or DEFAULT_PROGRAM_SIZE
    report = _build_bilan_report(record)
    position = bilan.preferred_position(record["tasks"])
    selection = settings["exercise_ids"]
    osteo_id = record.get("osteo_id")
    uncovered_zones: set[str] = set()
    candidate_filter = _osteo_candidate_filter(osteo_id, uncovered_zones) if osteo_id else None
    if selection is None:
        program = build_bilan_program(
            report, position, record["tasks"], size, candidate_filter=candidate_filter,
            extra_capsules=_db_capsules(validated_only=True),
        )
    else:
        full = build_bilan_program(
            report, position, record["tasks"], 200,
            extra_capsules=_db_capsules(validated_only=True),
        )
        program = select_program(
            selection, full, record["tasks"], extra_capsules=_db_capsules(validated_only=False)
        )
    warnings = list(report["warnings"])
    if uncovered_zones:
        osteo = accounts.get_user(osteo_id)
        osteo_name = osteo["name"] if osteo else "l'ostéopathe choisi"
        zones = ", ".join(ZONE_LABELS.get(zone, zone) for zone in sorted(uncovered_zones))
        warnings.append(
            f"Aucun exercice validé par {osteo_name} pour : "
            f"{zones}. Il doit valider (ou revalider) des fiches dans « Relecture des fiches » "
            "avant qu'elles soient proposées dans ce programme."
        )
    if any(item["basis"] == "declared" for item in program):
        warnings.append(
            "Une partie du programme vient des tâches saisies : sans vidéo, aucune posture n'est "
            "mesurée. Il se précise avec une analyse vidéo du poste."
        )
    return {
        "program": _annotate_program_videos(
            program, osteo_id, getattr(request.state, "user", None)
        ),
        "osteo_id": osteo_id,
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
    catalog = validation.load_effective_catalog()
    labels = validation.labels_for(catalog)
    return [
        {
            **{key: exercise[key] for key in _EXERCISE_SUMMARY_KEYS},
            "position": exercise.get("position", exercises.DEFAULT_POSITION),
            "fiche": exercise.get("fiche"),
            "validation": _public_label(labels[exercise["id"]]),
        }
        for exercise in catalog
    ]


def _public_label(label: dict) -> dict:
    """Étiquette sans identifiants de comptes (rien d'interne vers le patient)."""
    hidden = ("validator_ids", "validated_by_selected", "owner_id")
    return {key: value for key, value in label.items() if key not in hidden}


@app.get("/exercises/{exercise_id}")
async def get_exercise(exercise_id: str) -> dict:
    # L'id n'est jamais utilisé pour construire un chemin : on le cherche dans le
    # catalogue déjà chargé (pas de traversée de répertoire possible).
    exercise = validation.get_exercise(exercise_id)  # une fiche archivée reste lisible
    if exercise is not None:
        return {**exercise, "validation": _public_label(validation.label_for(exercise))}
    raise HTTPException(status_code=404, detail="Exercice introuvable.")


@app.get("/osteopaths")
async def list_osteopaths() -> list[dict]:
    """Comptes actifs avec le rôle ostéopathe, pour le choix sur le bilan."""
    return [
        {"id": user["id"], "name": user["name"]}
        for user in accounts.list_users()
        if user["active"] and validation.OSTEOPATH_ROLE in user["roles"]
    ]


class BilanOsteo(BaseModel):
    osteo_id: str | None = None


@app.put("/bilans/{bilan_id}/osteo")
async def put_bilan_osteo(bilan_id: str, body: BilanOsteo) -> dict:
    """Choisit l'ostéopathe du bilan (None : plus de choix, comportement d'avant)."""
    _get_bilan_or_404(bilan_id)
    if body.osteo_id is not None:
        chosen = accounts.get_user(body.osteo_id)
        if (
            chosen is None or not chosen["active"]
            or validation.OSTEOPATH_ROLE not in chosen["roles"]
        ):
            raise HTTPException(status_code=422, detail="Ostéopathe inconnu.")
    storage.set_bilan_osteo(bilan_id=bilan_id, osteo_id=body.osteo_id)
    return _get_bilan_or_404(bilan_id)


class ValidateBody(BaseModel):
    fingerprint: str
    formula: str
    animation_completed: bool
    # Vitesse de lecture utilisée pour voir l'animation en entier (1 = temps réel).
    playback_speed: float = 1.0


def _validation_response(exercise_id: str, label: dict | None = None) -> dict:
    exercise = validation.get_exercise(exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="Exercice introuvable.")
    return label or validation.label_for(exercise)


class SheetBody(BaseModel):
    """Contenu d'une fiche (voir exercises/README.md) ; champs posés par le serveur exclus."""

    model_config = {"extra": "allow"}


def _sheet_error(error: validation.ValidationError) -> HTTPException:
    return HTTPException(status_code=error.status, detail=str(error))


def _sheet_response(exercise: dict) -> dict:
    return {**exercise, "validation": _public_label(validation.label_for(exercise))}


@app.post("/exercises")
async def create_sheet(body: SheetBody, request: Request) -> dict:
    """Crée une fiche (ostéopathe). Elle naît sans validation."""
    try:
        return _sheet_response(sheets.create(getattr(request.state, "user", None), body.model_dump()))
    except validation.ValidationError as error:
        raise _sheet_error(error) from error


@app.post("/exercises/{exercise_id}/copy")
async def copy_sheet(exercise_id: str, request: Request) -> dict:
    """Copie une fiche : nouvel exercice sans validation, auteur d'origine conservé."""
    try:
        return _sheet_response(sheets.copy(getattr(request.state, "user", None), exercise_id))
    except validation.ValidationError as error:
        raise _sheet_error(error) from error


@app.put("/exercises/{exercise_id}")
async def update_sheet(exercise_id: str, body: SheetBody, request: Request) -> dict:
    """Modifie une fiche dont on est propriétaire : nouvelle version, sans validation."""
    try:
        return _sheet_response(
            sheets.update(getattr(request.state, "user", None), exercise_id, body.model_dump())
        )
    except validation.ValidationError as error:
        raise _sheet_error(error) from error


@app.post("/exercises/{exercise_id}/archive")
async def archive_sheet(exercise_id: str, request: Request) -> dict:
    try:
        return _sheet_response(
            sheets.set_archived(getattr(request.state, "user", None), exercise_id, True)
        )
    except validation.ValidationError as error:
        raise _sheet_error(error) from error


@app.post("/exercises/{exercise_id}/unarchive")
async def unarchive_sheet(exercise_id: str, request: Request) -> dict:
    try:
        return _sheet_response(
            sheets.set_archived(getattr(request.state, "user", None), exercise_id, False)
        )
    except validation.ValidationError as error:
        raise _sheet_error(error) from error


class ExchangeBundle(BaseModel):
    """Fichier d'échange (voir sheets.export_sheets) : le serveur revérifie tout."""

    model_config = {"extra": "allow"}


@app.get("/sheets/export")
async def export_my_sheets(
    request: Request, ids: str = Query("", max_length=100000),
    scope: str | None = Query(None, pattern="^(mine|all)$"),
) -> Response:
    """Fichier d'échange : les fiches `ids` (identifiants séparés par des virgules), ou, avec
    `scope`, toutes les fiches de l'ostéopathe (`mine`) ou tout le catalogue (`all`)."""
    user = getattr(request.state, "user", None)
    try:
        wanted = sheets.scope_ids(user, scope) if scope else [i for i in ids.split(",") if i.strip()]
        bundle = sheets.export_sheets(user, wanted)
    except validation.ValidationError as error:
        raise _sheet_error(error) from error
    day = datetime.now(timezone.utc).date().isoformat()
    return Response(
        json.dumps(bundle, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="fiches-tms-vision-{day}.json"'},
    )


@app.post("/sheets/import")
async def import_sheets_file(body: ExchangeBundle, request: Request) -> dict:
    """Importe un fichier d'échange : nouvelles fiches sans validation, appartenant à l'importateur."""
    try:
        report = sheets.import_sheets(getattr(request.state, "user", None), body.model_dump())
    except validation.ValidationError as error:
        raise _sheet_error(error) from error
    return {"report": report, "imported": sum(1 for item in report if item["status"] == "imported")}


@app.get("/sheets/mine")
async def list_my_sheets(request: Request) -> list[dict]:
    """Fiches créées ou copiées par l'ostéopathe connecté (archivées comprises)."""
    try:
        mine = sheets.list_mine(getattr(request.state, "user", None))
    except validation.ValidationError as error:
        raise _sheet_error(error) from error
    return [{**item["exercise"], "validation": _public_label(item["label"])} for item in mine]


@app.get("/sheets/all")
async def list_all_sheets(request: Request) -> list[dict]:
    """Toutes les fiches, de tous les auteurs, en lecture seule (administrateur)."""
    try:
        every = sheets.list_all(getattr(request.state, "user", None))
    except validation.ValidationError as error:
        raise _sheet_error(error) from error
    return [
        {**item["exercise"], "validation": _public_label(item["label"]), "owner_id": item["label"]["owner_id"]}
        for item in every
    ]


@app.get("/validation/queue")
async def get_validation_queue(
    request: Request, zone: str | None = None, fiches_only: bool = False
) -> dict:
    """File de relecture de l'ostéopathe connecté : fiches dont la version courante n'est pas
    validée par lui. Réservé au rôle ostéopathe."""
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Connexion requise.")
    if not validation.is_osteopath(user):
        raise HTTPException(status_code=403, detail="Réservé aux comptes ostéopathe.")
    if zone is not None and zone not in exercises.REGIONS:
        raise HTTPException(status_code=422, detail="Zone inconnue.")
    queue = validation.review_queue(user, zone=zone, fiches_only=fiches_only)
    return {"total": len(queue), "items": queue}


@app.get("/exercises/{exercise_id}/validation")
async def get_exercise_validation(exercise_id: str, request: Request) -> dict:
    """Étiquette de la version courante, formules acceptées et historique complet (validations et
    retraits). `can_validate` : le compte connecté est ostéopathe."""
    label = _validation_response(exercise_id)
    user = getattr(request.state, "user", None)
    return {
        **_public_label(label),
        "formulas": validation.FORMULAS,
        "max_playback_speed": validation.MAX_PLAYBACK_SPEED,
        "can_validate": validation.is_osteopath(user) and user["id"] not in label["validator_ids"],
        "can_withdraw": validation.is_osteopath(user) and user["id"] in label["validator_ids"],
        # Modifier / archiver : propriétaire de la fiche seulement ; copier : tout ostéopathe.
        "can_edit": validation.can_author(user) and label["owner_id"] == user["id"],
        "can_copy": validation.can_author(user),
        "history": validation.history(exercise_id),
    }


@app.post("/exercises/{exercise_id}/validate")
async def validate_exercise(exercise_id: str, body: ValidateBody, request: Request) -> dict:
    """Valide la version courante au nom du compte connecté : rôle ostéopathe exigé ici, côté API."""
    try:
        return validation.validate(
            getattr(request.state, "user", None), exercise_id, seen_fingerprint=body.fingerprint,
            formula=body.formula, animation_completed=body.animation_completed,
            playback_speed=body.playback_speed,
        )
    except validation.ValidationError as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error


@app.post("/exercises/{exercise_id}/withdraw-validation")
async def withdraw_exercise_validation(exercise_id: str, request: Request) -> dict:
    try:
        return validation.withdraw(getattr(request.state, "user", None), exercise_id)
    except validation.ValidationError as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error


@app.get("/version")
async def get_version() -> dict:
    return {"version": version.get_version()}


@app.get("/update")
async def get_update(request: Request, force: bool = False) -> dict:
    """Une version plus récente est-elle publiée ? Seulement dans l'application de bureau
    (TMS_CHECK_UPDATES=1) : un serveur installé par Docker se met à jour avec install.sh.
    `installable` : le bouton peut installer la mise à jour en un clic (application construite).
    `force=true` (administrateurs) : ignore le cache d'une heure ; `reachable` dit si GitHub a répondu."""
    if os.environ.get("TMS_CHECK_UPDATES") != "1":
        return {"available": False, "version": None, "url": None, "installable": False, "reachable": True,
                "supported": False}
    if force:
        user = getattr(request.state, "user", None)
        if auth_api.auth_required() and (user is None or "administrateur" not in user["roles"]):
            raise HTTPException(status_code=403, detail="Réservé aux administrateurs.")
        result = await run_in_threadpool(updates.check_now, version.get_version())
    else:
        result = {**await run_in_threadpool(updates.check, version.get_version()), "reachable": True}
    return {
        "available": result["available"], "version": result["version"], "url": result["url"],
        "installable": result["available"] and self_update.is_installable(),
        "reachable": result["reachable"], "supported": True,
    }


@app.post("/update/install")
async def install_update(request: Request) -> dict:
    """Sauvegarde les données, télécharge et installe la version publiée, puis relance l'application."""
    if os.environ.get("TMS_CHECK_UPDATES") != "1" or not self_update.is_installable():
        raise HTTPException(status_code=404, detail="Mise à jour en un clic indisponible ici.")
    # Une autre page web ouverte dans le navigateur ne doit pas pouvoir la déclencher.
    origin = request.headers.get("origin")
    if origin is not None and origin not in ALLOWED_ORIGINS:
        raise HTTPException(status_code=403, detail="Origine non autorisée.")
    # Une mise à jour redémarre l'application pour tout le monde : réservée aux administrateurs.
    user = getattr(request.state, "user", None)
    if auth_api.auth_required() and (user is None or "administrateur" not in user["roles"]):
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs.")
    self_update.start()
    return self_update.status()


@app.get("/update/status")
async def get_update_status() -> dict:
    return self_update.status()


@app.get("/library")
async def get_library() -> dict:
    try:
        data = library.load_library()
    except ValueError as error:
        raise HTTPException(status_code=500, detail=f"Bibliothèque invalide : {error}") from error
    return _with_cabinet_sheets(data)


# Zone de la carte du corps où ranger une fiche d'ostéopathe selon sa région d'exercice.
_BODY_MAP_ZONE = {
    "neck": "neck", "head": "neck", "trunk": "upper_back", "shoulder": "shoulder",
    "upper_arm": "shoulder", "lower_arm": "elbow", "hand": "wrist_hand", "hip": "hip",
    "thigh": "thigh", "lower_leg": "lower_leg", "foot": "ankle_foot",
}
CABINET_PATHOLOGY_ID = "fiches-cabinet"


def _with_cabinet_sheets(data: dict) -> dict:
    """Ajoute à chaque zone de la carte du corps une entrée « Fiches des ostéopathes » avec les
    fiches en base (copies, créations) validées par quelqu'un : un praticien ne voit pas les
    brouillons d'un ostéopathe."""
    sheets_by_zone: dict[str, list[str]] = {}
    for capsule in _db_capsules(validated_only=True):
        zone = _BODY_MAP_ZONE.get(capsule.zone)
        if zone:
            sheets_by_zone.setdefault(zone, []).append(capsule.id)
    if not sheets_by_zone:
        return data
    zones = []
    for zone in data["zones"]:
        ids = sheets_by_zone.get(zone["id"])
        if ids:
            zone = {**zone, "pathologies": [
                *zone["pathologies"],
                {"id": f"{CABINET_PATHOLOGY_ID}-{zone['id']}", "label": "Fiches des ostéopathes", "exercises": sorted(ids)},
            ]}
        zones.append(zone)
    return {**data, "zones": zones}


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
async def create_library_share(body: LibraryShareCreate, request: Request) -> dict:
    recipient = body.recipient_email.strip()
    if not _EMAIL_PATTERN.match(recipient):
        raise HTTPException(status_code=422, detail="Adresse email invalide.")

    catalog = {
        exercise["id"]: exercise
        for exercise in validation.load_effective_catalog(include_archived=True)
    }
    labels = validation.labels_for(list(catalog.values()))
    unknown = [item.exercise_id for item in body.items if item.exercise_id not in catalog]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Exercice introuvable : {unknown[0]}.")
    if len({item.exercise_id for item in body.items}) != len(body.items):
        raise HTTPException(status_code=422, detail="Exercice en double dans l'envoi.")

    user = getattr(request.state, "user", None)
    practitioner_name = _blank_to_none(body.practitioner_name) or (user["name"] if user else None)
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
        exercise_labels=[
            validation.describe_label(labels[item["exercise_id"]]) for item in items
        ],
    )

    # Réglages personnels du compte s'il en a, sinon l'adresse du cabinet avec le compte en Reply-To.
    try:
        service, reply_to = user_email.mailer_for(user)
    except mailer.MailerError:
        email_status = "failed"
    else:
        if reply_to:
            outgoing = dataclasses.replace(outgoing, reply_to=reply_to)
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
    catalog = {
        exercise["id"]: exercise
        for exercise in validation.load_effective_catalog(include_archived=True)
    }
    labels = validation.labels_for(list(catalog.values()))
    return {
        "created_at": share["created_at"],
        "practitioner_name": share["practitioner_name"],
        "message": share["message"],
        "items": [
            {
                "exercise": catalog[item["exercise_id"]], "note": item["note"],
                "validation": _public_label(labels[item["exercise_id"]]),
            }
            for item in share["items"]
            if item["exercise_id"] in catalog
        ],
    }


class ProgramSettingsBody(BaseModel):
    size: int | None = Field(default=None, ge=1, le=MAX_PROGRAM_SIZE)
    # None : programme automatique ; une liste : exercices choisis par le praticien, dans l'ordre.
    exercise_ids: list[str] | None = Field(default=None, max_length=MAX_PROGRAM_SIZE * 2)


@app.put("/bilans/{bilan_id}/program")
async def put_bilan_program_settings(
    bilan_id: str, body: ProgramSettingsBody, request: Request
) -> dict:
    """Enregistre le nombre d'exercices et, éventuellement, la sélection du praticien."""
    _get_bilan_or_404(bilan_id)
    known = {capsule.id for capsule in [*CAPSULES, *_db_capsules(validated_only=False)]}
    unknown = [i for i in body.exercise_ids or [] if i not in known]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Exercices inconnus : {', '.join(unknown)}")
    storage.set_program_settings(
        bilan_id=bilan_id, size=body.size,
        exercise_ids=list(dict.fromkeys(body.exercise_ids)) if body.exercise_ids is not None else None,
    )
    return await get_bilan_program(bilan_id, request, size=None)
