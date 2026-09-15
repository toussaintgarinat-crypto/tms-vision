# Capture web + API FastAPI (Phase 2, tranche 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre de filmer une personne depuis un navigateur, faire tourner le pipeline RULA de la Phase 1 via une API FastAPI, et afficher le résultat (vidéo annotée + score) dans une page web — pour valider enfin le PoC sur une vraie personne et poser la première brique de la Phase 2.

**Architecture:** Le cœur du pipeline `cli.py` (capture → pose → angles → score RULA → overlay → export) est extrait en une fonction pure `analyze_video()` réutilisable. Un endpoint FastAPI synchrone reçoit un clip vidéo uploadé, appelle cette fonction, et renvoie le résumé + les liens vers les fichiers produits. Une page Next.js unique enregistre un clip via la caméra du navigateur (`getUserMedia`/`MediaRecorder`), l'envoie à l'API, puis affiche le résultat.

**Tech Stack:** Python 3.11 (venv dédié), MediaPipe, OpenCV, FastAPI, uvicorn, pytest ; Next.js 16 (App Router, TypeScript, Tailwind), React.

## Global Constraints

- Python 3.11 dans le venv dédié du projet (MediaPipe incompatible avec Python 3.14) — toute commande Python passe par `venv/bin/python`, `venv/bin/pip`, `venv/bin/pytest`.
- Enregistrer puis analyser uniquement — pas de temps réel, pas de streaming frame par frame (voir spec, décision de cadrage).
- Capture caméra 2D uniquement (`getUserMedia`) — pas de LiDAR/profondeur dans cette tranche.
- Pas de base de données, pas de queue de jobs — traitement synchrone, résultats sur le système de fichiers (`outputs/`).
- Frontend Next.js (App Router, TypeScript) dans un nouveau dossier `web/`.
- Tout se développe directement sur `main`, pas de branche ni de worktree.
- `pytest.ini` fixe `pythonpath = src` et `testpaths = tests` : les tests Python s'exécutent avec `venv/bin/pytest` depuis la racine du projet (`~/Desktop/TMS vision`).
- Spec de référence : `docs/superpowers/specs/2026-09-14-web-capture-fastapi-design.md`.

---

## Task 1: Extraire le pipeline en fonction réutilisable (`pipeline.py`)

**Files:**
- Create: `src/tms_vision/pipeline.py`
- Create: `tests/test_pipeline.py`
- Modify: `src/tms_vision/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Produces: `tms_vision.pipeline.analyze_video(source: str, side: str, load_kg: float, wrist_twist: str, output_dir: str) -> AnalysisResult`
- Produces: `tms_vision.pipeline.AnalysisResult` — dataclass `{empty: bool, video_path: Path | None = None, csv_path: Path | None = None, summary_json_path: Path | None = None}`
- Produces: `tms_vision.pipeline._RunningMean` (déplacé tel quel depuis `cli.py`, inchangé)
- Consumes (inchangé) : `tms_vision.capture.FrameSource`, `tms_vision.pose_estimation.PoseEstimator`, `tms_vision.angles.compute_joint_angles`, `tms_vision.rula.scoring.compute_rula_score`/`detect_muscle_use`, `tms_vision.overlay.draw_overlay`, `tms_vision.export.FrameRecord`/`ResultsExporter`

- [ ] **Step 1: Écrire les tests de `pipeline.py` (qui n'existe pas encore)**

Créer `tests/test_pipeline.py` :

```python
import numpy as np
import cv2
import pytest

from tms_vision.pipeline import analyze_video, AnalysisResult, _RunningMean
from tms_vision.capture import Frame


def test_running_mean_starts_at_none():
    mean = _RunningMean()
    assert mean.value is None


def test_running_mean_computes_average_incrementally():
    mean = _RunningMean()
    mean.update(2.0)
    assert mean.value == 2.0
    mean.update(4.0)
    assert mean.value == 3.0
    mean.update(9.0)
    assert mean.value == 5.0


class _EmptyFrameSource:
    """Simule une source vidéo qui s'ouvre correctement mais ne produit aucune
    frame -- le cas que le garde-fou "aucune frame capturée" doit intercepter
    avant toute tentative d'ouverture d'un cv2.VideoWriter en taille (0, 0)."""

    def __init__(self, *_args, **_kwargs):
        pass

    def fps(self):
        return 30.0

    def __iter__(self):
        return iter([])

    def release(self):
        pass


def test_analyze_video_with_zero_frames_returns_empty_result_without_writing(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr("tms_vision.pipeline.FrameSource", _EmptyFrameSource)

    output_dir = tmp_path / "outputs"
    result = analyze_video(
        source="webcam", side="right", load_kg=0.0, wrist_twist="normal",
        output_dir=str(output_dir),
    )

    assert result == AnalysisResult(empty=True)
    captured = capsys.readouterr()
    assert "Aucune frame capturée" in captured.err
    assert list(output_dir.glob("*_annotated.mp4")) == []
    assert list(output_dir.glob("*_frames.csv")) == []
    assert list(output_dir.glob("*_summary.json")) == []


def test_analyze_video_end_to_end_on_a_blank_synthetic_video(tmp_path):
    video_path = tmp_path / "synthetic.mp4"
    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (64, 64)
    )
    for _ in range(3):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()

    output_dir = tmp_path / "outputs"
    result = analyze_video(
        source=str(video_path), side="right", load_kg=0.0, wrist_twist="normal",
        output_dir=str(output_dir),
    )

    assert result.empty is False
    assert result.video_path.exists()
    assert result.csv_path.exists()
    assert result.summary_json_path.exists()


class _InterruptingFrameSource:
    """Simule une source vidéo qui produit quelques frames puis reçoit un
    Ctrl+C (KeyboardInterrupt) pendant la boucle de capture."""

    def __init__(self, *_args, **_kwargs):
        self.released = False

    def fps(self):
        return 30.0

    def __iter__(self):
        for i in range(2):
            yield Frame(
                index=i, timestamp_seconds=i / 30.0,
                image=np.zeros((64, 64, 3), dtype=np.uint8),
            )
        raise KeyboardInterrupt

    def release(self):
        self.released = True


def test_analyze_video_with_keyboard_interrupt_during_capture_still_writes_partial_outputs(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr("tms_vision.pipeline.FrameSource", _InterruptingFrameSource)

    output_dir = tmp_path / "outputs"
    result = analyze_video(
        source="webcam", side="right", load_kg=0.0, wrist_twist="normal",
        output_dir=str(output_dir),
    )

    captured = capsys.readouterr()
    assert "Capture interrompue" in captured.out
    assert result.empty is False
    assert result.video_path.exists()
    assert result.csv_path.exists()
    assert result.summary_json_path.exists()


def test_analyze_video_raises_on_missing_file():
    with pytest.raises(FileNotFoundError):
        analyze_video(
            source="does-not-exist.mp4", side="right", load_kg=0.0,
            wrist_twist="normal", output_dir="outputs",
        )
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `cd ~/Desktop/"TMS vision" && venv/bin/pytest tests/test_pipeline.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'tms_vision.pipeline'`

- [ ] **Step 3: Créer `src/tms_vision/pipeline.py`**

```python
"""Pipeline Phase 1 réutilisable : capture -> pose -> angles -> score RULA ->
overlay vidéo + export CSV/JSON.

Extrait de cli.py pour être appelable aussi bien depuis la CLI que depuis
l'API FastAPI (api.py), sans dupliquer la logique (voir
docs/superpowers/specs/2026-09-14-web-capture-fastapi-design.md).
"""
import secrets
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import cv2

from tms_vision.capture import FrameSource
from tms_vision.pose_estimation import PoseEstimator
from tms_vision.angles import compute_joint_angles
from tms_vision.rula.scoring import compute_rula_score, detect_muscle_use
from tms_vision.overlay import draw_overlay
from tms_vision.export import FrameRecord, ResultsExporter

WRIST_TWIST_CODES = {"normal": 1, "extreme": 2}


class _RunningMean:
    """Moyenne mobile incrémentale simple (compteur + somme cumulée), utilisée
    pour donner à compute_joint_angles() une référence stable de la hauteur
    "au repos" de l'épaule (shoulder_baseline_y) plutôt que la position de la
    seule frame courante."""

    def __init__(self) -> None:
        self._count = 0
        self._total = 0.0

    def update(self, value: float) -> None:
        self._count += 1
        self._total += value

    @property
    def value(self) -> float | None:
        if self._count == 0:
            return None
        return self._total / self._count


@dataclass
class AnalysisResult:
    empty: bool
    video_path: Path | None = None
    csv_path: Path | None = None
    summary_json_path: Path | None = None


def analyze_video(
    source: str, side: str, load_kg: float, wrist_twist: str, output_dir: str
) -> AnalysisResult:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"

    wrist_twist_code = WRIST_TWIST_CODES[wrist_twist]

    frame_source = FrameSource(source)
    estimator = PoseEstimator()

    frames = []
    try:
        for frame in frame_source:
            frames.append(frame)
    except KeyboardInterrupt:
        print("\nCapture interrompue par l'utilisateur, traitement des frames déjà capturées...")
    finally:
        frame_source.release()

    if not frames:
        print("Aucune frame capturée, rien à analyser.", file=sys.stderr)
        estimator.close()
        return AnalysisResult(empty=True)

    per_frame_angles = []
    posture_load_history: list[tuple[float, float]] = []
    shoulder_key = f"{side.upper()}_SHOULDER"
    shoulder_y_baseline = _RunningMean()

    for frame in frames:
        pose_result = estimator.process(frame.image)
        angles = None
        if pose_result.landmarks is not None:
            # Baseline = moyenne des frames PRÉCÉDENTES uniquement (pas la
            # frame courante) ; sur la toute première frame détectée, aucune
            # donnée antérieure n'existe -> None (repli sur le comportement
            # historique pour cette frame-là seulement).
            angles = compute_joint_angles(
                pose_result.landmarks, side=side, shoulder_baseline_y=shoulder_y_baseline.value
            )
            current_shoulder = pose_result.landmarks.get(shoulder_key)
            if current_shoulder is not None:
                shoulder_y_baseline.update(current_shoulder.y)
        per_frame_angles.append((frame, pose_result, angles))
        if angles is not None:
            posture_load = angles.trunk_flexion_deg + angles.upper_arm_flexion_deg
            posture_load_history.append((frame.timestamp_seconds, posture_load))

    estimator.close()

    muscle_use_score = 1 if detect_muscle_use(posture_load_history) else 0

    # `frames` est garanti non vide ici : le garde-fou `if not frames: ...
    # return` ci-dessus a déjà court-circuité la fonction sinon.
    height, width = frames[0].image.shape[:2]
    video_path = output_path / f"{run_id}_annotated.mp4"
    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), frame_source.fps() or 30.0, (width, height)
    )

    csv_path = output_path / f"{run_id}_frames.csv"
    summary_json_path = output_path / f"{run_id}_summary.json"
    exporter = ResultsExporter(str(csv_path), str(summary_json_path))

    for frame, pose_result, angles in per_frame_angles:
        score = None
        if angles is not None:
            score = compute_rula_score(
                angles, wrist_twist=wrist_twist_code, load_kg=load_kg, muscle_use_score=muscle_use_score
            )
        annotated = draw_overlay(frame.image, pose_result.landmarks, score)
        writer.write(annotated)
        exporter.add_frame(
            FrameRecord(
                frame_index=frame.index,
                timestamp_seconds=frame.timestamp_seconds,
                detected=angles is not None,
                angles=angles,
                score=score,
            )
        )

    writer.release()
    exporter.finalize()

    return AnalysisResult(
        empty=False, video_path=video_path, csv_path=csv_path, summary_json_path=summary_json_path
    )
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `venv/bin/pytest tests/test_pipeline.py -v`
Expected: PASS — 6 tests passés

- [ ] **Step 5: Réécrire `src/tms_vision/cli.py` en fin wrapper**

```python
"""Point d'entrée CLI : parse les arguments et délègue le pipeline à
tms_vision.pipeline.analyze_video() (voir ce module pour la logique complète).

Conseil de prise de vue : pour des angles fiables (flexion/extension du cou,
du tronc et du bras), filmer la personne DE PROFIL plutôt que de face.
"""
import argparse
import sys

from tms_vision.pipeline import analyze_video


def _non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("--load-kg doit être positif ou nul")
    return parsed


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyse ergonomique RULA d'une vidéo de poste de travail."
    )
    parser.add_argument("--source", required=True, help='"webcam" ou chemin vers un fichier vidéo')
    parser.add_argument("--side", choices=["left", "right"], default="right")
    parser.add_argument("--load-kg", type=_non_negative_float, default=0.0)
    parser.add_argument("--wrist-twist", choices=["normal", "extreme"], default="normal")
    parser.add_argument("--output-dir", default="outputs")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> None:
    result = analyze_video(
        source=args.source,
        side=args.side,
        load_kg=args.load_kg,
        wrist_twist=args.wrist_twist,
        output_dir=args.output_dir,
    )
    if result.empty:
        return
    print(f"Vidéo annotée : {result.video_path}")
    print(f"Export CSV/JSON : {result.csv_path}, {result.summary_json_path}")


def main() -> None:
    args = parse_args(sys.argv[1:])
    try:
        run(args)
    except (FileNotFoundError, RuntimeError) as error:
        print(f"Erreur : {error}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        # Un premier Ctrl+C pendant la capture est déjà intercepté à
        # l'intérieur de analyze_video() et traite les frames déjà capturées.
        # Un second Ctrl+C pendant la boucle de traitement qui suit (pose/
        # score/écriture vidéo) n'est en revanche pas couvert par ce
        # garde-fou interne : on l'attrape ici pour éviter une traceback
        # brute sans sortie utile.
        print("Traitement interrompu par l'utilisateur.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Réécrire `tests/test_cli.py`**

```python
import numpy as np
import cv2
import pytest

from tms_vision.cli import parse_args, run, main


def test_parse_args_defaults():
    args = parse_args(["--source", "webcam"])
    assert args.source == "webcam"
    assert args.side == "right"
    assert args.load_kg == 0.0
    assert args.wrist_twist == "normal"
    assert args.output_dir == "outputs"


def test_parse_args_rejects_negative_load():
    with pytest.raises(SystemExit):
        parse_args(["--source", "webcam", "--load-kg", "-5"])


def test_parse_args_rejects_invalid_side():
    with pytest.raises(SystemExit):
        parse_args(["--source", "webcam", "--side", "up"])


def test_parse_args_rejects_invalid_wrist_twist():
    with pytest.raises(SystemExit):
        parse_args(["--source", "webcam", "--wrist-twist", "sideways"])


def test_run_prints_output_paths_on_success(tmp_path, capsys):
    video_path = tmp_path / "synthetic.mp4"
    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (64, 64)
    )
    for _ in range(3):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()

    output_dir = tmp_path / "outputs"
    args = parse_args(["--source", str(video_path), "--output-dir", str(output_dir)])
    run(args)

    captured = capsys.readouterr()
    assert "Vidéo annotée :" in captured.out
    assert "Export CSV/JSON :" in captured.out


def test_main_catches_keyboard_interrupt_during_processing_loop_and_exits_cleanly(
    tmp_path, monkeypatch, capsys
):
    # Un second Ctrl+C survenant APRÈS la capture (donc pendant la boucle
    # pose/score/écriture vidéo) ne doit pas produire de traceback brute. On
    # simule ce second Ctrl+C en interrompant draw_overlay, appelé une fois
    # par frame dans cette boucle -- désormais dans pipeline.py.
    video_path = tmp_path / "synthetic.mp4"
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (64, 64))
    for _ in range(3):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()

    def _raise_keyboard_interrupt(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("tms_vision.pipeline.draw_overlay", _raise_keyboard_interrupt)

    output_dir = tmp_path / "outputs"
    monkeypatch.setattr(
        "sys.argv",
        ["tms-vision", "--source", str(video_path), "--output-dir", str(output_dir)],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Traitement interrompu par l'utilisateur." in captured.err
```

- [ ] **Step 7: Lancer la suite complète, vérifier qu'elle passe**

Run: `venv/bin/pytest -v`
Expected: PASS — tous les tests passent, aucun échec

- [ ] **Step 8: Commit**

```bash
git add src/tms_vision/pipeline.py src/tms_vision/cli.py tests/test_pipeline.py tests/test_cli.py
git commit -m "refactor: extraire le pipeline Phase 1 en fonction réutilisable analyze_video()"
```

---

## Task 2: API FastAPI (`POST /analyses`)

**Files:**
- Modify: `requirements.txt`
- Create: `src/tms_vision/api.py`
- Create: `tests/test_api.py`

**Interfaces:**
- Consumes: `tms_vision.pipeline.analyze_video()` et `AnalysisResult` (Task 1)
- Produces: `tms_vision.api.app` (instance FastAPI), `tms_vision.api.OUTPUT_DIR` (constante `Path`, patchable en test), endpoint `POST /analyses` (multipart : `file`, `side`, `load_kg`, `wrist_twist`) → JSON `{summary, annotated_video_url, csv_url}`, fichiers servis sous `/outputs/*`

- [ ] **Step 1: Ajouter les dépendances FastAPI à `requirements.txt`**

```
mediapipe>=0.10.14
opencv-python>=4.9.0
numpy>=1.26,<2.0
pytest>=8.0
fastapi>=0.115
uvicorn[standard]>=0.30
python-multipart>=0.0.9
httpx>=0.27
```

- [ ] **Step 2: Installer les dépendances**

Run: `cd ~/Desktop/"TMS vision" && venv/bin/pip install -r requirements.txt`
Expected: `Successfully installed fastapi-... uvicorn-... python-multipart-... httpx-...` (parmi les autres paquets déjà installés)

- [ ] **Step 3: Écrire les tests de l'API (qui n'existe pas encore)**

Créer `tests/test_api.py` :

```python
import cv2
import numpy as np
from fastapi.testclient import TestClient

from tms_vision.api import app


def _write_synthetic_video(path):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (64, 64))
    for _ in range(3):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()


def test_create_analysis_with_no_detectable_person_returns_empty_summary(tmp_path, monkeypatch):
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    client = TestClient(app)
    with open(video_path, "rb") as video_file:
        response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["detected_frame_count"] == 0
    assert body["summary"]["max_score"] == 0
    assert body["annotated_video_url"].startswith("/outputs/")
    assert body["csv_url"].startswith("/outputs/")


def test_create_analysis_rejects_invalid_side(tmp_path, monkeypatch):
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    client = TestClient(app)
    with open(video_path, "rb") as video_file:
        response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={"side": "up", "load_kg": "0", "wrist_twist": "normal"},
        )

    assert response.status_code == 422


def test_create_analysis_rejects_unreadable_video(tmp_path, monkeypatch):
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    garbage_path = tmp_path / "not_a_video.mp4"
    garbage_path.write_bytes(b"this is not a real video file")

    client = TestClient(app)
    with open(garbage_path, "rb") as video_file:
        response = client.post(
            "/analyses",
            files={"file": ("not_a_video.mp4", video_file, "video/mp4")},
            data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
        )

    assert response.status_code == 422
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils échouent**

Run: `venv/bin/pytest tests/test_api.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'tms_vision.api'`

- [ ] **Step 5: Créer `src/tms_vision/api.py`**

```python
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
```

- [ ] **Step 6: Lancer les tests, vérifier qu'ils passent**

Run: `venv/bin/pytest tests/test_api.py -v`
Expected: PASS — 3 tests passés

- [ ] **Step 7: Lancer la suite complète, vérifier qu'elle passe**

Run: `venv/bin/pytest -v`
Expected: PASS — tous les tests passent, aucun échec

- [ ] **Step 8: Commit**

```bash
git add requirements.txt src/tms_vision/api.py tests/test_api.py
git commit -m "feat: API FastAPI POST /analyses exposant le pipeline Phase 1"
```

---

## Task 3: Page Next.js de capture et de résultat

**Files:**
- Create: `web/` (scaffold Next.js complet)
- Modify: `web/app/page.tsx`

**Interfaces:**
- Consumes: l'API `POST /analyses` de Task 2 (`http://localhost:8000` par défaut, via `process.env.NEXT_PUBLIC_API_URL`)

- [ ] **Step 1: Scaffolder l'app Next.js**

Run (depuis `~/Desktop/"TMS vision"`) :
```bash
npx --yes create-next-app@latest web --ts --app --tailwind --eslint --use-npm --disable-git --yes
```
Expected: crée le dossier `web/` avec un projet Next.js (App Router, TypeScript, Tailwind) prêt à l'emploi, se termine sans erreur.

- [ ] **Step 2: Lire les instructions générées pour ce projet Next.js avant d'écrire du code**

`create-next-app` génère par défaut un `web/AGENTS.md` qui pointe vers `web/node_modules/next/dist/docs/` pour les conventions/breaking changes de la version installée. Lire ce fichier (et le guide App Router qu'il référence si présent) avant l'étape suivante — le code du Step 3 suppose des conventions React/Next App Router stables (composant client `"use client"`, hooks `useState`/`useRef`, export par défaut d'une fonction de page) ; n'ajuster que si la documentation générée indique un changement cassant sur exactement ces points.

- [ ] **Step 3: Écrire `web/app/page.tsx`**

```tsx
"use client";

import { useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Side = "left" | "right";
type WristTwist = "normal" | "extreme";

type AnalysisSummary = {
  frame_count: number;
  detected_frame_count: number;
  max_score: number;
  average_score: number;
  time_by_action_level: Record<string, number>;
};

type AnalysisResponse = {
  summary: AnalysisSummary;
  annotated_video_url: string;
  csv_url: string;
};

export default function Home() {
  const videoPreviewRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const [cameraReady, setCameraReady] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordedFile, setRecordedFile] = useState<File | null>(null);
  const [side, setSide] = useState<Side>("right");
  const [loadKg, setLoadKg] = useState("0");
  const [wristTwist, setWristTwist] = useState<WristTwist>("normal");
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResponse | null>(null);

  async function startCamera() {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      streamRef.current = stream;
      if (videoPreviewRef.current) {
        videoPreviewRef.current.srcObject = stream;
      }
      setCameraReady(true);
    } catch {
      setError(
        "Impossible d'accéder à la caméra. Vérifiez les permissions du navigateur et que la page est servie en HTTPS ou localhost."
      );
    }
  }

  function startRecording() {
    if (!streamRef.current) return;
    const mimeType = MediaRecorder.isTypeSupported("video/mp4")
      ? "video/mp4"
      : "video/webm";
    const recorder = new MediaRecorder(streamRef.current, { mimeType });
    chunksRef.current = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: mimeType });
      const extension = mimeType.includes("mp4") ? "mp4" : "webm";
      setRecordedFile(new File([blob], `capture.${extension}`, { type: mimeType }));
    };
    recorder.start();
    recorderRef.current = recorder;
    setRecording(true);
    setResult(null);
    setError(null);
  }

  function stopRecording() {
    recorderRef.current?.stop();
    setRecording(false);
  }

  async function analyze() {
    if (!recordedFile) return;
    setAnalyzing(true);
    setError(null);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append("file", recordedFile);
      formData.append("side", side);
      formData.append("load_kg", loadKg);
      formData.append("wrist_twist", wristTwist);

      const response = await fetch(`${API_URL}/analyses`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? `Erreur serveur (${response.status})`);
      }

      const data: AnalysisResponse = await response.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur inconnue pendant l'analyse.");
    } finally {
      setAnalyzing(false);
    }
  }

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 p-8">
      <h1 className="text-2xl font-semibold">TMS Vision — Vérification RULA</h1>

      <video
        ref={videoPreviewRef}
        autoPlay
        muted
        playsInline
        className="w-full rounded-lg bg-black"
      />

      {!cameraReady && (
        <button onClick={startCamera} className="rounded bg-black px-4 py-2 text-white">
          Démarrer la caméra
        </button>
      )}

      {cameraReady && !recording && (
        <button onClick={startRecording} className="rounded bg-red-600 px-4 py-2 text-white">
          Démarrer l&apos;enregistrement
        </button>
      )}

      {recording && (
        <button onClick={stopRecording} className="rounded bg-gray-700 px-4 py-2 text-white">
          Arrêter l&apos;enregistrement
        </button>
      )}

      {recordedFile && (
        <section className="flex flex-col gap-4 rounded border p-4">
          <label className="flex flex-col gap-1">
            Côté filmé
            <select
              value={side}
              onChange={(event) => setSide(event.target.value as Side)}
              className="rounded border p-2"
            >
              <option value="right">Droit</option>
              <option value="left">Gauche</option>
            </select>
          </label>

          <label className="flex flex-col gap-1">
            Charge tenue (kg)
            <input
              type="number"
              min="0"
              step="0.5"
              value={loadKg}
              onChange={(event) => setLoadKg(event.target.value)}
              className="rounded border p-2"
            />
          </label>

          <label className="flex flex-col gap-1">
            Torsion du poignet
            <select
              value={wristTwist}
              onChange={(event) => setWristTwist(event.target.value as WristTwist)}
              className="rounded border p-2"
            >
              <option value="normal">Normale</option>
              <option value="extreme">Extrême</option>
            </select>
          </label>

          <button
            onClick={analyze}
            disabled={analyzing}
            className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
          >
            {analyzing ? "Analyse en cours..." : "Analyser"}
          </button>
        </section>
      )}

      {error && <p className="text-red-600">{error}</p>}

      {result && (
        <section className="flex flex-col gap-4 rounded border p-4">
          <h2 className="text-lg font-semibold">Résultat</h2>
          <video
            src={`${API_URL}${result.annotated_video_url}`}
            controls
            className="w-full rounded-lg bg-black"
          />
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt>Frames analysées</dt>
            <dd>{result.summary.frame_count}</dd>
            <dt>Frames avec pose détectée</dt>
            <dd>{result.summary.detected_frame_count}</dd>
            <dt>Score RULA max</dt>
            <dd>{result.summary.max_score}</dd>
            <dt>Score RULA moyen</dt>
            <dd>{result.summary.average_score.toFixed(1)}</dd>
          </dl>
          <a href={`${API_URL}${result.csv_url}`} className="text-blue-600 underline">
            Télécharger le CSV détaillé
          </a>
        </section>
      )}
    </main>
  );
}
```

- [ ] **Step 4: Vérifier que le projet compile (type-check + build)**

Run: `cd web && npm run build`
Expected: build Next.js réussi (`✓ Compiled successfully`), aucune erreur TypeScript

- [ ] **Step 5: Commit**

```bash
cd ~/Desktop/"TMS vision"
git add web/
git commit -m "feat: page Next.js de capture caméra et affichage du résultat RULA"
```

---

## Task 4 (MANUEL — à exécuter par l'utilisateur du projet, pas par un subagent)

Cette tâche demande une vraie personne devant une vraie caméra : aucun exécuteur automatisé (subagent y compris) n'y a accès. C'est aussi la vérification qui était en attente depuis la fin de la Phase 1.

- [ ] **Step 1: Démarrer l'API**

Run (depuis `~/Desktop/"TMS vision"`) : `PYTHONPATH=src venv/bin/uvicorn tms_vision.api:app --reload --port 8000`
Expected: `Uvicorn running on http://127.0.0.1:8000`

- [ ] **Step 2: Démarrer le frontend**

Run (dans un autre terminal) : `cd ~/Desktop/"TMS vision"/web && npm run dev`
Expected: `Local: http://localhost:3000`

- [ ] **Step 3: Vérification manuelle**

Ouvrir `http://localhost:3000`, autoriser la caméra, se filmer **de profil** quelques secondes, arrêter l'enregistrement, remplir le formulaire (côté, charge, torsion poignet) et cliquer "Analyser". Vérifier :
- La requête aboutit (pas d'erreur affichée) — si elle échoue avec un message évoquant un fichier illisible, c'est probablement le risque identifié dans la spec (format `MediaRecorder` non décodable par `cv2.VideoCapture`) ; noter le format utilisé (webm/mp4) et le navigateur.
- Le squelette se superpose correctement sur la vidéo annotée renvoyée.
- Le score RULA affiché correspond visuellement à la posture filmée (poste penché → score plus élevé, posture neutre → score bas).

---

## Self-Review

1. **Couverture de la spec** : capture web (Task 3) ✓, backend FastAPI réutilisant le pipeline sans duplication (Task 1 + 2) ✓, enregistrer-puis-analyser synchrone sans DB/queue (Task 2, pas de job queue introduite) ✓, gestion d'erreurs (422 sur vidéo illisible/vide/paramètres invalides, Task 2 tests) ✓, vérification humaine en attente depuis la Phase 1 (Task 4) ✓. Hors périmètre de la spec (LiDAR, DB, auth, déploiement, floutage RGPD, calibrage des seuils) — correctement absents des tâches.
2. **Scan de placeholders** : aucun "TBD"/"TODO", tout le code est complet et exécutable tel quel.
3. **Cohérence des types** : `analyze_video(source, side, load_kg, wrist_twist, output_dir) -> AnalysisResult` identique dans `pipeline.py`, `cli.py`, `api.py` et les deux fichiers de tests ; `AnalysisResult{empty, video_path, csv_path, summary_json_path}` utilisé de façon cohérente partout où il apparaît.
