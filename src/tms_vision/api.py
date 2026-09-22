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
from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from tms_vision import storage
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
    load_kg: float = Form(..., ge=0),
    wrist_twist: Literal["normal", "extreme"] = Form(...),
    worker_label: str | None = Form(None),
    poste_label: str | None = Form(None),
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
    load_kg: float = Form(..., ge=0),
    wrist_twist: Literal["normal", "extreme"] = Form(...),
    worker_label: str | None = Form(None),
    poste_label: str | None = Form(None),
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


@app.get("/analyses/{analysis_id}/video")
async def get_analysis_video(analysis_id: str) -> Response:
    video_bytes = storage.get_video_bytes(analysis_id)
    if video_bytes is None:
        raise HTTPException(status_code=404, detail="Analyse introuvable.")
    return Response(
        content=video_bytes, media_type="video/mp4",
        headers={"Content-Disposition": f'attachment; filename="{analysis_id}_annotated.mp4"'},
    )


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
