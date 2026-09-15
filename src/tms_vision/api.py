"""API FastAPI : expose le pipeline Phase 1 (tms_vision.pipeline) pour la
capture web. Reçoit un clip vidéo enregistré dans le navigateur, lance
l'analyse RULA existante, renvoie le résumé et les liens vers les fichiers
produits (voir docs/superpowers/specs/2026-09-14-web-capture-fastapi-design.md)."""
import json
import shutil
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from tms_vision.pipeline import analyze_video

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["POST"],
    allow_headers=["*"],
)

app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")


@app.post("/analyses")
async def create_analysis(
    file: UploadFile = File(...),
    side: Literal["left", "right"] = Form(...),
    load_kg: float = Form(...),
    wrist_twist: Literal["normal", "extreme"] = Form(...),
) -> dict:
    suffix = Path(file.filename or "").suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        upload_path = Path(tmp.name)

    try:
        result = analyze_video(
            source=str(upload_path),
            side=side,
            load_kg=load_kg,
            wrist_twist=wrist_twist,
            output_dir=str(OUTPUT_DIR),
        )
    except (FileNotFoundError, RuntimeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    finally:
        upload_path.unlink(missing_ok=True)

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
