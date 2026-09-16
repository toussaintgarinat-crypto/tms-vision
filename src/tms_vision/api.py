"""API FastAPI : expose le pipeline Phase 1 (tms_vision.pipeline) pour la
capture web. Reçoit un clip vidéo (enregistré dans le navigateur en un seul
POST /analyses, ou importé et envoyé par chunks via POST /uploads + PUT
.../chunks/{index} + POST .../complete), lance l'analyse RULA existante,
renvoie le résumé et les liens vers les fichiers produits (voir
docs/superpowers/specs/2026-09-14-web-capture-fastapi-design.md et
docs/superpowers/specs/2026-09-15-web-upload-chunked-design.md)."""
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Literal

import cv2
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from tms_vision.pipeline import analyze_video

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
    # GET n'a pas besoin d'être listé ici : un fetch GET "simple" (sans en-tête
    # personnalisé/Authorization) ne déclenche pas de préflight CORS et
    # /outputs/{filename} fonctionne déjà sans lui (voir commit 98795e4, qui a
    # retiré un ajout de "GET" fait par erreur). Ne le rajouter que si un futur
    # appel GET a besoin d'un en-tête non simple.
    allow_methods=["POST", "PUT"],
    allow_headers=["*"],
)


@app.get("/outputs/{filename}")
async def get_output_file(filename: str) -> FileResponse:
    """Sert un fichier produit par le pipeline. Résout OUTPUT_DIR à chaque
    requête (plutôt qu'un StaticFiles monté une fois à l'import) pour rester
    cohérent avec la lecture d'OUTPUT_DIR faite par create_analysis, y
    compris quand OUTPUT_DIR est patché en test."""
    file_path = OUTPUT_DIR / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Fichier introuvable.")
    return FileResponse(file_path, filename=file_path.name)


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
    video_path: Path, side: str, load_kg: float, wrist_twist: str
) -> dict:
    """Appelle analyze_video sur un fichier déjà sur disque et construit la
    réponse JSON standard. Partagé par create_analysis (upload direct) et
    complete_upload (upload par chunks) : les deux finissent par produire un
    seul fichier vidéo local, traité de façon identique à partir de ce point."""
    _reject_if_estimated_too_large(video_path)
    try:
        result = await run_in_threadpool(
            analyze_video,
            source=str(video_path),
            side=side,
            load_kg=load_kg,
            wrist_twist=wrist_twist,
            output_dir=str(OUTPUT_DIR),
        )
    except (FileNotFoundError, RuntimeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if result.empty:
        raise HTTPException(
            status_code=422,
            detail="Vidéo illisible ou vide : aucune frame n'a pu être extraite.",
        )

    summary = json.loads(result.summary_json_path.read_text())
    return {
        "summary": summary,
        "annotated_video_url": f"/outputs/{result.video_path.name}",
        "csv_url": f"/outputs/{result.csv_path.name}",
    }


@app.post("/analyses")
async def create_analysis(
    file: UploadFile = File(...),
    side: Literal["left", "right"] = Form(...),
    load_kg: float = Form(..., ge=0),
    wrist_twist: Literal["normal", "extreme"] = Form(...),
) -> dict:
    suffix = Path(file.filename or "").suffix or ".webm"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    upload_path = Path(tmp.name)
    try:
        with tmp:
            shutil.copyfileobj(file.file, tmp)
        return await _analyze_and_build_response(upload_path, side, load_kg, wrist_twist)
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
    survivre à un redémarrage d'uvicorn --reload en cours d'upload."""
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
    """Reçoit un chunk d'un fichier en cours d'upload. Écrit le chunk dans
    la session d'upload créée par start_upload."""
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
        return await _analyze_and_build_response(upload_path, side, load_kg, wrist_twist)
    finally:
        upload_path.unlink(missing_ok=True)
        shutil.rmtree(session_dir, ignore_errors=True)
