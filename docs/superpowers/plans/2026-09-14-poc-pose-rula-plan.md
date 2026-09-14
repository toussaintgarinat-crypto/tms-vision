# PoC Pipeline Pose Estimation & Score RULA — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python pipeline that reads a video (webcam or file), extracts posture via MediaPipe Pose, computes joint angles, and produces a complete official RULA score (Tables A/B/C) per frame, with an annotated output video and CSV/JSON export.

**Architecture:** Modular package (`src/tms_vision/`) with one file per pipeline stage — capture, pose estimation, angle math, RULA tables, RULA scoring, overlay rendering, data export, CLI orchestration. Each module is unit-testable in isolation with synthetic inputs; no module depends on a live camera or MediaPipe model to be tested.

**Tech Stack:** Python 3.11 (venv), MediaPipe Pose, OpenCV, NumPy, pytest.

## Global Constraints

- Python version: **3.11** (MediaPipe does not support 3.14, the system default). All commands in this plan use the project venv's interpreter, never bare `python3`.
- RULA tables must match `docs/superpowers/specs/2026-09-14-poc-pose-rula-design.md` and are sourced from the Cornell University RULA worksheet (Prof. Alan Hedge, Feb. 2001), itself citing McAtamney, L. & Corlett, E.N. (1993), *Applied Ergonomics*, 24(2), 91-99. Do not alter the table values given in Task 5 — they have been verified digit-for-digit against that source.
- Legs score is fixed at 1 ("jambes soutenues") per the approved spec — this is a documented PoC limitation, not a bug.
- Wrist twist and load are manual CLI inputs (`--wrist-twist`, `--load-kg`) per the approved spec — a monocular RGB camera cannot measure these.
- All angle math uses 2D image-plane coordinates (x, y only) from MediaPipe Pose landmarks; the `z` field is not used (too noisy on a single RGB camera without depth).
- All docstrings and CLI help text should be in French to match the project's existing documentation (`README.md`, spec).
- Commit after every task with a message prefixed `feat(tms-vision):`.

---

## File Structure

```
TMS vision/
├── requirements.txt
├── .python-version                         → "3.11"
├── src/tms_vision/
│   ├── __init__.py
│   ├── capture.py                           # FrameSource: webcam or file → frames
│   ├── pose_estimation.py                   # PoseEstimator: MediaPipe wrapper
│   ├── angles.py                            # compute_joint_angles(): landmarks → JointAngles
│   ├── rula/
│   │   ├── __init__.py
│   │   ├── tables.py                        # TABLE_A/B/C + lookup functions
│   │   └── scoring.py                       # JointAngles + manual params → RulaScore
│   ├── overlay.py                           # draw_overlay(): skeleton + score badge
│   ├── export.py                            # FrameRecord export to CSV/JSON + summary
│   └── cli.py                               # argument parsing + orchestration
├── tests/
│   ├── __init__.py
│   ├── test_capture.py
│   ├── test_angles.py
│   ├── test_rula_tables.py
│   ├── test_rula_scoring.py
│   └── test_export.py
├── samples/                                  # test videos (gitignored)
└── outputs/                                  # generated videos + exports (gitignored)
```

---

### Task 1: Project scaffolding — venv, dependencies, package skeleton

**Files:**
- Create: `requirements.txt`
- Create: `.python-version`
- Create: `.gitignore`
- Create: `src/tms_vision/__init__.py`
- Create: `src/tms_vision/rula/__init__.py`
- Create: `tests/__init__.py`
- Create: `pytest.ini`

**Interfaces:**
- Produces: a working `venv/` at the project root, activated as `venv/bin/python`, with `mediapipe`, `opencv-python`, `numpy`, `pytest` installed. All later tasks run commands through `venv/bin/python` / `venv/bin/pytest`.

- [ ] **Step 1: Install Python 3.11 via Homebrew if not already present**

Run: `brew list --versions python@3.11`
Expected: prints a version like `python@3.11 3.11.15`. If it prints nothing, run `brew install python@3.11` first.

- [ ] **Step 2: Create the project venv with Python 3.11**

Run (from `/Users/garinat_t/Desktop/TMS vision`):
```bash
/usr/local/opt/python@3.11/bin/python3.11 -m venv venv
venv/bin/python --version
```
Expected: `Python 3.11.15` (or similar 3.11.x).

- [ ] **Step 3: Write `.python-version`**

```
3.11
```

- [ ] **Step 4: Write `requirements.txt`**

```
mediapipe>=0.10.14
opencv-python>=4.9.0
numpy>=1.26,<2.0
pytest>=8.0
```

- [ ] **Step 5: Write `.gitignore`**

```
venv/
__pycache__/
*.pyc
samples/
outputs/
.pytest_cache/
```

- [ ] **Step 6: Install dependencies**

Run: `venv/bin/pip install -r requirements.txt`
Expected: exits 0, `mediapipe` and `opencv-python` installed successfully (NumPy is pinned `<2.0` because MediaPipe 0.10.x wheels are built against NumPy 1.x).

- [ ] **Step 7: Create package skeleton**

`src/tms_vision/__init__.py`:
```python
```
(empty file — marks the package)

`src/tms_vision/rula/__init__.py`:
```python
```
(empty file)

`tests/__init__.py`:
```python
```
(empty file)

- [ ] **Step 8: Write `pytest.ini` so tests can import `tms_vision` without installing the package**

```ini
[pytest]
pythonpath = src
testpaths = tests
```

- [ ] **Step 9: Verify pytest runs (no tests yet, should report "no tests ran")**

Run: `venv/bin/pytest -q`
Expected: `no tests ran` (exit code 5) — this confirms pytest and the pythonpath config work before any real test exists.

- [ ] **Step 10: Create `samples/` and `outputs/` directories with `.gitkeep`**

Run: `mkdir -p samples outputs && touch samples/.gitkeep outputs/.gitkeep`

- [ ] **Step 11: Commit**

```bash
git add requirements.txt .python-version .gitignore pytest.ini src/ tests/ samples/.gitkeep outputs/.gitkeep
git commit -m "feat(tms-vision): scaffold project with Python 3.11 venv and package layout"
```

---

### Task 2: `capture.py` — frame source (webcam or video file)

**Files:**
- Create: `src/tms_vision/capture.py`
- Test: `tests/test_capture.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `@dataclass Frame(index: int, timestamp_seconds: float, image: np.ndarray)`
  - `class FrameSource: def __init__(self, source: str)`, `def __iter__(self) -> Iterator[Frame]`, `def fps(self) -> float`, `def release(self) -> None`
  - `source="webcam"` opens `cv2.VideoCapture(0)`; any other string is treated as a file path.
  - Raises `FileNotFoundError` if `source` is not `"webcam"` and the path does not exist.
  - Raises `RuntimeError` if the capture device/file cannot be opened.

- [ ] **Step 1: Write the failing test for file-not-found**

```python
# tests/test_capture.py
import pytest
from tms_vision.capture import FrameSource


def test_missing_file_raises_file_not_found():
    with pytest.raises(FileNotFoundError):
        FrameSource("samples/does_not_exist.mp4")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/pytest tests/test_capture.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tms_vision.capture'`

- [ ] **Step 3: Write `src/tms_vision/capture.py`**

```python
"""Source de frames vidéo : fichier ou webcam."""
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np


@dataclass
class Frame:
    index: int
    timestamp_seconds: float
    image: np.ndarray


class FrameSource:
    """Fournit des frames depuis la webcam (source="webcam") ou un fichier vidéo."""

    def __init__(self, source: str):
        if source != "webcam" and not Path(source).exists():
            raise FileNotFoundError(f"Fichier vidéo introuvable : {source}")

        capture_target = 0 if source == "webcam" else source
        self._capture = cv2.VideoCapture(capture_target)
        if not self._capture.isOpened():
            raise RuntimeError(f"Impossible d'ouvrir la source vidéo : {source}")

        self._fps = self._capture.get(cv2.CAP_PROP_FPS) or 30.0

    def fps(self) -> float:
        return self._fps

    def __iter__(self) -> Iterator[Frame]:
        index = 0
        while True:
            ok, image = self._capture.read()
            if not ok:
                break
            timestamp_seconds = index / self._fps
            yield Frame(index=index, timestamp_seconds=timestamp_seconds, image=image)
            index += 1

    def release(self) -> None:
        self._capture.release()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/pytest tests/test_capture.py -v`
Expected: 1 passed.

- [ ] **Step 5: Write the failing test for a real video file, using a synthetic file generated with OpenCV**

```python
# tests/test_capture.py (append)
import numpy as np
import cv2


def test_reads_frames_from_a_real_video_file(tmp_path):
    video_path = tmp_path / "synthetic.mp4"
    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (32, 32)
    )
    for _ in range(5):
        writer.write(np.zeros((32, 32, 3), dtype=np.uint8))
    writer.release()

    source = FrameSource(str(video_path))
    frames = list(source)
    source.release()

    assert len(frames) == 5
    assert frames[0].index == 0
    assert frames[4].index == 4
    assert frames[0].image.shape == (32, 32, 3)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `venv/bin/pytest tests/test_capture.py -v`
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add src/tms_vision/capture.py tests/test_capture.py
git commit -m "feat(tms-vision): add FrameSource for webcam and video file capture"
```

---

### Task 3: `pose_estimation.py` — MediaPipe Pose wrapper

**Files:**
- Create: `src/tms_vision/pose_estimation.py`
- Test: `tests/test_pose_estimation.py`

**Interfaces:**
- Consumes: `Frame.image` (a `np.ndarray`, BGR) from Task 2 — but this module does not import `capture.py`, it just accepts a raw `np.ndarray`.
- Produces:
  - `@dataclass Landmark(x: float, y: float, z: float, visibility: float)`
  - `class PoseResult: landmarks: dict[str, Landmark] | None` — `None` when no pose detected.
  - `class PoseEstimator: def __init__(self, min_visibility: float = 0.5)`, `def process(self, image_bgr: np.ndarray) -> PoseResult`, `def close(self) -> None`
  - Dict keys are MediaPipe `PoseLandmark` enum names, e.g. `"LEFT_SHOULDER"`, `"RIGHT_ELBOW"`, `"NOSE"`. Landmarks whose `visibility < min_visibility` are **excluded** from the dict (later modules must handle missing keys).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pose_estimation.py
import numpy as np
from tms_vision.pose_estimation import PoseEstimator


def test_blank_frame_returns_no_landmarks():
    estimator = PoseEstimator()
    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    result = estimator.process(blank)
    estimator.close()

    assert result.landmarks is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/pytest tests/test_pose_estimation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tms_vision.pose_estimation'`

- [ ] **Step 3: Write `src/tms_vision/pose_estimation.py`**

```python
"""Wrapper autour de MediaPipe Pose : extraction des 33 keypoints par frame."""
from dataclasses import dataclass

import mediapipe as mp
import numpy as np


@dataclass
class Landmark:
    x: float
    y: float
    z: float
    visibility: float


@dataclass
class PoseResult:
    landmarks: dict[str, Landmark] | None


class PoseEstimator:
    """Détecte la posture humaine sur une frame BGR via MediaPipe Pose."""

    def __init__(self, min_visibility: float = 0.5):
        self._min_visibility = min_visibility
        self._pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def process(self, image_bgr: np.ndarray) -> PoseResult:
        image_rgb = image_bgr[:, :, ::-1]
        results = self._pose.process(image_rgb)

        if results.pose_landmarks is None:
            return PoseResult(landmarks=None)

        landmarks: dict[str, Landmark] = {}
        pose_landmark_enum = mp.solutions.pose.PoseLandmark
        for landmark_id, raw in enumerate(results.pose_landmarks.landmark):
            if raw.visibility < self._min_visibility:
                continue
            name = pose_landmark_enum(landmark_id).name
            landmarks[name] = Landmark(
                x=raw.x, y=raw.y, z=raw.z, visibility=raw.visibility
            )

        return PoseResult(landmarks=landmarks or None)

    def close(self) -> None:
        self._pose.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/pytest tests/test_pose_estimation.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/tms_vision/pose_estimation.py tests/test_pose_estimation.py
git commit -m "feat(tms-vision): add MediaPipe Pose wrapper"
```

---

### Task 4: `angles.py` — joint angle computation from landmarks

**Files:**
- Create: `src/tms_vision/angles.py`
- Test: `tests/test_angles.py`

**Interfaces:**
- Consumes: `Landmark` (name, `x`, `y`, `z`, `visibility` fields) from Task 3. This module takes a plain `dict[str, Landmark]`, not a `PoseResult`.
- Produces:
  - `@dataclass JointAngles` with fields: `neck_flexion_deg: float`, `neck_twisted: bool`, `neck_side_bending: bool`, `trunk_flexion_deg: float`, `trunk_twisted: bool`, `trunk_side_bending: bool`, `upper_arm_flexion_deg: float`, `upper_arm_abducted: bool`, `upper_arm_shoulder_raised: bool`, `lower_arm_angle_deg: float`, `lower_arm_across_midline: bool`, `wrist_flexion_deg: float`, `wrist_bent_from_midline: bool`, `arm_supported: bool`
  - `def compute_joint_angles(landmarks: dict[str, Landmark], side: str, shoulder_baseline_y: float | None = None) -> JointAngles | None` — `side` is `"left"` or `"right"`. Returns `None` if any required landmark is missing.
  - Required landmarks (both sides always, since torso center needs both): `LEFT_SHOULDER`, `RIGHT_SHOULDER`, `LEFT_HIP`, `RIGHT_HIP`, `NOSE`, plus, for the given `side`: `{SIDE}_SHOULDER`, `{SIDE}_ELBOW`, `{SIDE}_WRIST`, `{SIDE}_EAR`, `{SIDE}_INDEX`. (`{SIDE}_SHOULDER` is already covered by the always-required pair.)

**Geometric conventions** (all computed in 2D image coordinates, y grows downward):
- "Facing direction" `facing = +1 if nose.x >= shoulder_mid.x else -1` — used to give flexion/extension a sign for the neck and upper arm, assuming a side-view capture (documented in `README.md` capture guidance).
- `torso_length = distance(shoulder_mid, hip_mid)` — used to normalize the shoulder-raise and midline thresholds so they scale with the person's size in frame.
- Angles between two vectors use `arccos(dot(v1, v2) / (|v1| * |v2|))`, clipped to `[-1, 1]` before `arccos` to avoid `nan` from floating-point overshoot.

- [ ] **Step 1: Write the failing tests using synthetic landmarks with known geometry**

```python
# tests/test_angles.py
import math
from tms_vision.pose_estimation import Landmark
from tms_vision.angles import compute_joint_angles


def _lm(x, y, z=0.0, visibility=1.0):
    return Landmark(x=x, y=y, z=z, visibility=visibility)


def _base_landmarks():
    """Personne debout, de profil, tournée vers +x, posture neutre (angles ~0)."""
    return {
        "LEFT_SHOULDER": _lm(0.50, 0.30),
        "RIGHT_SHOULDER": _lm(0.50, 0.30),
        "LEFT_HIP": _lm(0.50, 0.55),
        "RIGHT_HIP": _lm(0.50, 0.55),
        "NOSE": _lm(0.52, 0.20),
        "LEFT_EAR": _lm(0.51, 0.22),
        "RIGHT_EAR": _lm(0.51, 0.22),
        "LEFT_ELBOW": _lm(0.50, 0.45),
        "LEFT_WRIST": _lm(0.50, 0.60),
        "LEFT_INDEX": _lm(0.50, 0.63),
    }


def test_neutral_posture_gives_near_zero_flexion_angles():
    landmarks = _base_landmarks()
    result = compute_joint_angles(landmarks, side="left")

    assert result is not None
    assert abs(result.trunk_flexion_deg) < 5.0
    assert abs(result.neck_flexion_deg) < 10.0


def test_trunk_flexed_forward_90_degrees_is_detected():
    landmarks = _base_landmarks()
    # Le buste bascule à l'horizontale (flexion à 90°) : les épaules
    # s'éloignent horizontalement des hanches au lieu d'être au-dessus.
    landmarks["LEFT_SHOULDER"] = _lm(0.80, 0.55)
    landmarks["RIGHT_SHOULDER"] = _lm(0.80, 0.55)
    result = compute_joint_angles(landmarks, side="left")

    assert result is not None
    assert 80.0 <= result.trunk_flexion_deg <= 100.0


def test_elbow_fully_extended_gives_180_degree_lower_arm_angle():
    landmarks = _base_landmarks()
    # Épaule, coude et poignet alignés verticalement -> bras tendu (180°).
    landmarks["LEFT_ELBOW"] = _lm(0.50, 0.45)
    landmarks["LEFT_WRIST"] = _lm(0.50, 0.60)
    result = compute_joint_angles(landmarks, side="left")

    assert result is not None
    assert result.lower_arm_angle_deg > 170.0


def test_missing_required_landmark_returns_none():
    landmarks = _base_landmarks()
    del landmarks["LEFT_WRIST"]
    result = compute_joint_angles(landmarks, side="left")

    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_angles.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tms_vision.angles'`

- [ ] **Step 3: Write `src/tms_vision/angles.py`**

```python
"""Calcul des angles articulaires RULA à partir des landmarks MediaPipe Pose.

Convention : coordonnées image 2D (x, y), y croît vers le bas. La capture est
supposée filmée de profil (voir README, section "Conseils de prise de vue"),
ce qui permet de donner un signe (flexion/extension) aux angles du cou et du
bras. Le tronc utilise uniquement une magnitude (RULA ne distingue pas
d'extension du tronc dans sa table).
"""
from dataclasses import dataclass

import numpy as np

from tms_vision.pose_estimation import Landmark

SIDE_BEND_THRESHOLD_DEG = 10.0
ABDUCTION_WIDTH_RATIO = 1.3
SHOULDER_RAISE_RATIO = 0.05
MIDLINE_MARGIN_RATIO = 0.05


@dataclass
class JointAngles:
    neck_flexion_deg: float
    neck_twisted: bool
    neck_side_bending: bool
    trunk_flexion_deg: float
    trunk_twisted: bool
    trunk_side_bending: bool
    upper_arm_flexion_deg: float
    upper_arm_abducted: bool
    upper_arm_shoulder_raised: bool
    lower_arm_angle_deg: float
    lower_arm_across_midline: bool
    wrist_flexion_deg: float
    wrist_bent_from_midline: bool
    arm_supported: bool


def _xy(landmark: Landmark) -> np.ndarray:
    return np.array([landmark.x, landmark.y])


def _midpoint(a: Landmark, b: Landmark) -> np.ndarray:
    return (_xy(a) + _xy(b)) / 2.0


def _angle_between(v1: np.ndarray, v2: np.ndarray) -> float:
    norm_product = np.linalg.norm(v1) * np.linalg.norm(v2)
    if norm_product == 0:
        return 0.0
    cosine = np.clip(np.dot(v1, v2) / norm_product, -1.0, 1.0)
    return float(np.degrees(np.arccos(cosine)))


def _line_angle_from_horizontal(a: np.ndarray, b: np.ndarray) -> float:
    delta = b - a
    return float(np.degrees(np.arctan2(delta[1], delta[0])))


REQUIRED_COMMON = ["LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_HIP", "RIGHT_HIP", "NOSE"]
REQUIRED_PER_SIDE = ["SHOULDER", "ELBOW", "WRIST", "EAR", "INDEX"]


def compute_joint_angles(
    landmarks: dict[str, Landmark], side: str, shoulder_baseline_y: float | None = None
) -> JointAngles | None:
    side_prefix = side.upper()
    required = list(REQUIRED_COMMON) + [f"{side_prefix}_{name}" for name in REQUIRED_PER_SIDE]
    if any(name not in landmarks for name in required):
        return None

    shoulder_mid = _midpoint(landmarks["LEFT_SHOULDER"], landmarks["RIGHT_SHOULDER"])
    hip_mid = _midpoint(landmarks["LEFT_HIP"], landmarks["RIGHT_HIP"])
    torso_length = float(np.linalg.norm(shoulder_mid - hip_mid)) or 1e-6

    nose = _xy(landmarks["NOSE"])
    facing = 1.0 if nose[0] >= shoulder_mid[0] else -1.0

    side_shoulder = _xy(landmarks[f"{side_prefix}_SHOULDER"])
    elbow = _xy(landmarks[f"{side_prefix}_ELBOW"])
    wrist = _xy(landmarks[f"{side_prefix}_WRIST"])
    ear = _xy(landmarks[f"{side_prefix}_EAR"])
    index_finger = _xy(landmarks[f"{side_prefix}_INDEX"])

    vertical = np.array([0.0, -1.0])

    # --- Cou ---
    head_vec = ear - shoulder_mid
    neck_magnitude = _angle_between(head_vec, vertical)
    forward_component = (ear[0] - shoulder_mid[0]) * facing
    neck_flexion_deg = neck_magnitude if forward_component >= 0 else -neck_magnitude

    left_ear = _xy(landmarks["LEFT_EAR"]) if "LEFT_EAR" in landmarks else ear
    right_ear = _xy(landmarks["RIGHT_EAR"]) if "RIGHT_EAR" in landmarks else ear
    ear_line_angle = _line_angle_from_horizontal(left_ear, right_ear)
    shoulder_line_angle = _line_angle_from_horizontal(
        _xy(landmarks["LEFT_SHOULDER"]), _xy(landmarks["RIGHT_SHOULDER"])
    )
    neck_side_bending = abs(ear_line_angle - shoulder_line_angle) > SIDE_BEND_THRESHOLD_DEG
    ear_mid_x = (left_ear[0] + right_ear[0]) / 2.0
    ear_distance = abs(left_ear[0] - right_ear[0]) or 1e-6
    neck_twisted = abs(nose[0] - ear_mid_x) / ear_distance > 0.15

    # --- Tronc ---
    torso_vec = shoulder_mid - hip_mid
    trunk_flexion_deg = _angle_between(torso_vec, vertical)
    trunk_side_bending = abs(shoulder_line_angle) > SIDE_BEND_THRESHOLD_DEG

    # --- Bras (épaule -> coude) ---
    upper_arm_vec = elbow - side_shoulder
    upper_arm_magnitude = _angle_between(upper_arm_vec, vertical)
    upper_arm_forward = (elbow[0] - side_shoulder[0]) * facing
    upper_arm_flexion_deg = upper_arm_magnitude if upper_arm_forward >= 0 else -upper_arm_magnitude

    shoulder_width = float(
        np.linalg.norm(_xy(landmarks["LEFT_SHOULDER"]) - _xy(landmarks["RIGHT_SHOULDER"]))
    ) or 1e-6
    upper_arm_abducted = abs(elbow[0] - hip_mid[0]) > ABDUCTION_WIDTH_RATIO * shoulder_width

    baseline_y = shoulder_baseline_y if shoulder_baseline_y is not None else side_shoulder[1]
    upper_arm_shoulder_raised = (baseline_y - side_shoulder[1]) > SHOULDER_RAISE_RATIO * torso_length

    # --- Avant-bras (coude) ---
    forearm_vec = wrist - elbow
    upper_arm_from_elbow = side_shoulder - elbow
    lower_arm_angle_deg = _angle_between(upper_arm_from_elbow, forearm_vec)
    lower_arm_across_midline = abs(wrist[0] - shoulder_mid[0]) > MIDLINE_MARGIN_RATIO * torso_length and (
        (wrist[0] - shoulder_mid[0]) * (side_shoulder[0] - shoulder_mid[0]) < 0
    )

    # --- Poignet ---
    hand_vec = index_finger - wrist
    wrist_flexion_deg = 180.0 - _angle_between(forearm_vec, hand_vec)

    return JointAngles(
        neck_flexion_deg=neck_flexion_deg,
        neck_twisted=neck_twisted,
        neck_side_bending=neck_side_bending,
        trunk_flexion_deg=trunk_flexion_deg,
        trunk_twisted=False,  # rotation axiale du tronc = phénomène en profondeur (z), non fiable en capture 2D de profil (limite PoC)
        trunk_side_bending=trunk_side_bending,
        upper_arm_flexion_deg=upper_arm_flexion_deg,
        upper_arm_abducted=upper_arm_abducted,
        upper_arm_shoulder_raised=upper_arm_shoulder_raised,
        lower_arm_angle_deg=lower_arm_angle_deg,
        lower_arm_across_midline=lower_arm_across_midline,
        wrist_flexion_deg=wrist_flexion_deg,
        wrist_bent_from_midline=False,  # non détectable de façon fiable en monoculaire (limite PoC)
        arm_supported=False,  # non détectable sans segmentation de surface (limite PoC)
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_angles.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/tms_vision/angles.py tests/test_angles.py
git commit -m "feat(tms-vision): compute RULA joint angles from pose landmarks"
```

---

### Task 5: `rula/tables.py` — official RULA lookup tables

**Files:**
- Create: `src/tms_vision/rula/tables.py`
- Test: `tests/test_rula_tables.py`

**Interfaces:**
- Consumes: nothing (pure lookup tables + functions taking plain ints).
- Produces:
  - `def lookup_table_a(upper_arm: int, lower_arm: int, wrist: int, wrist_twist: int) -> int`
  - `def lookup_table_b(neck: int, trunk: int, legs: int) -> int`
  - `def lookup_table_c(wrist_arm_score: int, neck_trunk_leg_score: int) -> int`
  - All three clamp out-of-range inputs to the table's valid bounds (e.g. `upper_arm` clamped to `[1, 6]`) rather than raising, since sub-scores computed in Task 6 can exceed table bounds after adding adjustments.

- [ ] **Step 1: Write the failing tests, using the worked example from the Cornell RULA worksheet (McAtamney & Corlett, 1993) as reference anchors**

```python
# tests/test_rula_tables.py
from tms_vision.rula.tables import lookup_table_a, lookup_table_b, lookup_table_c


def test_table_a_worked_example_from_cornell_worksheet():
    # Upper arm=3, lower arm=2, wrist=4, wrist twist=2 -> Posture Score A = 5
    assert lookup_table_a(upper_arm=3, lower_arm=2, wrist=4, wrist_twist=2) == 5


def test_table_a_first_cell_is_minimum_score():
    assert lookup_table_a(upper_arm=1, lower_arm=1, wrist=1, wrist_twist=1) == 1


def test_table_a_last_cell_is_maximum_score():
    assert lookup_table_a(upper_arm=6, lower_arm=3, wrist=4, wrist_twist=2) == 9


def test_table_b_worked_example_from_cornell_worksheet():
    # Neck=3, trunk=2, legs=1 -> Posture Score B = 3
    assert lookup_table_b(neck=3, trunk=2, legs=1) == 3


def test_table_b_first_cell_is_minimum_score():
    assert lookup_table_b(neck=1, trunk=1, legs=1) == 1


def test_table_c_worked_example_from_cornell_worksheet():
    # Wrist & Arm Score=7, Neck/Trunk/Leg Score=5 -> Final RULA Score = 7
    assert lookup_table_c(wrist_arm_score=7, neck_trunk_leg_score=5) == 7


def test_table_c_clamps_scores_above_the_table_bounds():
    # Table C only goes up to row "8+" and column "7+"; scores above that
    # (possible once muscle use + force/load are added) must clamp, not crash.
    assert lookup_table_c(wrist_arm_score=13, neck_trunk_leg_score=11) == 7


def test_table_a_clamps_out_of_range_inputs():
    assert lookup_table_a(upper_arm=9, lower_arm=1, wrist=1, wrist_twist=1) == lookup_table_a(
        upper_arm=6, lower_arm=1, wrist=1, wrist_twist=1
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_rula_tables.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tms_vision.rula.tables'`

- [ ] **Step 3: Write `src/tms_vision/rula/tables.py`**

```python
"""Tables de scoring RULA officielles (Tables A, B, C).

Source : RULA Employee Assessment Worksheet, Prof. Alan Hedge, Cornell
University (Feb. 2001), citant McAtamney, L. & Corlett, E.N. (1993),
"RULA: a survey method for the investigation of work-related upper limb
disorders", Applied Ergonomics, 24(2), 91-99.

Chaque valeur a été vérifiée contre l'exemple travaillé du document source :
upper_arm=3, lower_arm=2, wrist=4, wrist_twist=2 -> Table A = 5
neck=3, trunk=2, legs=1 -> Table B = 3
wrist_arm_score=7, neck_trunk_leg_score=5 -> Table C = 7
"""

# TABLE_A[upper_arm-1][lower_arm-1] = [[wrist1_twist1, wrist1_twist2],
#                                       [wrist2_twist1, wrist2_twist2],
#                                       [wrist3_twist1, wrist3_twist2],
#                                       [wrist4_twist1, wrist4_twist2]]
TABLE_A = [
    [  # upper_arm = 1
        [[1, 2], [2, 2], [2, 3], [3, 3]],  # lower_arm = 1
        [[2, 2], [2, 2], [3, 3], [3, 3]],  # lower_arm = 2
        [[2, 3], [2, 3], [3, 3], [4, 4]],  # lower_arm = 3
    ],
    [  # upper_arm = 2
        [[2, 2], [2, 3], [3, 3], [4, 4]],  # lower_arm = 1
        [[2, 2], [2, 3], [3, 3], [4, 4]],  # lower_arm = 2
        [[2, 3], [3, 3], [3, 4], [4, 5]],  # lower_arm = 3
    ],
    [  # upper_arm = 3
        [[2, 3], [3, 3], [4, 4], [5, 5]],  # lower_arm = 1
        [[2, 3], [3, 3], [4, 4], [5, 5]],  # lower_arm = 2
        [[2, 3], [3, 4], [4, 4], [5, 5]],  # lower_arm = 3
    ],
    [  # upper_arm = 4
        [[3, 4], [4, 4], [4, 4], [5, 5]],  # lower_arm = 1
        [[3, 4], [4, 4], [4, 4], [5, 5]],  # lower_arm = 2
        [[3, 4], [4, 5], [5, 5], [6, 6]],  # lower_arm = 3
    ],
    [  # upper_arm = 5
        [[5, 5], [5, 5], [5, 6], [6, 7]],  # lower_arm = 1
        [[5, 6], [6, 6], [6, 7], [7, 7]],  # lower_arm = 2
        [[6, 6], [6, 7], [7, 7], [7, 8]],  # lower_arm = 3
    ],
    [  # upper_arm = 6
        [[7, 7], [7, 7], [7, 8], [8, 9]],  # lower_arm = 1
        [[7, 8], [8, 8], [8, 9], [9, 9]],  # lower_arm = 2
        [[9, 9], [9, 9], [9, 9], [9, 9]],  # lower_arm = 3
    ],
]

# TABLE_B[neck-1][trunk-1] = [legs1, legs2]
TABLE_B = [
    [[1, 3], [2, 3], [3, 4], [5, 5], [6, 6], [7, 7]],  # neck = 1
    [[2, 3], [2, 3], [4, 5], [5, 5], [6, 7], [7, 7]],  # neck = 2
    [[3, 3], [3, 4], [4, 5], [5, 6], [6, 7], [7, 7]],  # neck = 3
    [[5, 5], [5, 6], [6, 7], [7, 7], [7, 7], [8, 8]],  # neck = 4
    [[7, 7], [7, 7], [7, 8], [8, 8], [8, 8], [8, 8]],  # neck = 5
    [[8, 8], [8, 8], [8, 8], [8, 9], [9, 9], [9, 9]],  # neck = 6
]

# TABLE_C[wrist_arm_score-1][neck_trunk_leg_score-1], row/col 8 = "8+"/"7+"
TABLE_C = [
    [1, 2, 3, 3, 4, 5, 5],  # wrist_arm_score = 1
    [2, 2, 3, 4, 4, 5, 5],  # wrist_arm_score = 2
    [3, 3, 3, 4, 4, 5, 6],  # wrist_arm_score = 3
    [3, 3, 3, 4, 5, 6, 6],  # wrist_arm_score = 4
    [4, 4, 4, 5, 6, 7, 7],  # wrist_arm_score = 5
    [4, 4, 5, 6, 6, 7, 7],  # wrist_arm_score = 6
    [5, 5, 6, 6, 7, 7, 7],  # wrist_arm_score = 7
    [5, 5, 6, 7, 7, 7, 7],  # wrist_arm_score = 8+
]


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))


def lookup_table_a(upper_arm: int, lower_arm: int, wrist: int, wrist_twist: int) -> int:
    ua = _clamp(upper_arm, 1, 6) - 1
    la = _clamp(lower_arm, 1, 3) - 1
    w = _clamp(wrist, 1, 4) - 1
    twist = _clamp(wrist_twist, 1, 2) - 1
    return TABLE_A[ua][la][w][twist]


def lookup_table_b(neck: int, trunk: int, legs: int) -> int:
    n = _clamp(neck, 1, 6) - 1
    t = _clamp(trunk, 1, 6) - 1
    legs_index = _clamp(legs, 1, 2) - 1
    return TABLE_B[n][t][legs_index]


def lookup_table_c(wrist_arm_score: int, neck_trunk_leg_score: int) -> int:
    row = _clamp(wrist_arm_score, 1, 8) - 1
    col = _clamp(neck_trunk_leg_score, 1, 7) - 1
    return TABLE_C[row][col]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_rula_tables.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/tms_vision/rula/tables.py tests/test_rula_tables.py
git commit -m "feat(tms-vision): add official RULA tables A/B/C verified against Cornell worksheet"
```

---

### Task 6: `rula/scoring.py` — full RULA scoring engine

**Files:**
- Create: `src/tms_vision/rula/scoring.py`
- Test: `tests/test_rula_scoring.py`

**Interfaces:**
- Consumes: `JointAngles` from Task 4 (all fields), `lookup_table_a`/`lookup_table_b`/`lookup_table_c` from Task 5.
- Produces:
  - `@dataclass RulaScore` with fields: `upper_arm: int`, `lower_arm: int`, `wrist: int`, `wrist_twist: int`, `posture_score_a: int`, `neck: int`, `trunk: int`, `legs: int`, `posture_score_b: int`, `muscle_use_score: int`, `force_load_score: int`, `wrist_arm_score: int`, `neck_trunk_leg_score: int`, `final_score: int`, `action_level: str`
  - `def classify_upper_arm(angle_deg: float, shoulder_raised: bool, abducted: bool, supported: bool) -> int`
  - `def classify_lower_arm(angle_deg: float, across_midline: bool) -> int`
  - `def classify_wrist(flexion_deg: float, bent_from_midline: bool) -> int`
  - `def classify_neck(flexion_deg: float, twisted: bool, side_bending: bool) -> int`
  - `def classify_trunk(flexion_deg: float, twisted: bool, side_bending: bool) -> int`
  - `def force_load_score(load_kg: float, is_static_or_repetitive: bool) -> int`
  - `def action_level(final_score: int) -> str` — returns one of `"acceptable"`, `"investigation_recommandee"`, `"investigation_et_changement_bientot"`, `"changement_immediat"` matching the README's colour matrix (1-2 / 3-4 / 5-6 / 7).
  - `LEGS_SCORE = 1` (module-level constant, documented PoC assumption).
  - `def compute_rula_score(angles: JointAngles, wrist_twist: int, load_kg: float, muscle_use_score: int) -> RulaScore` — `wrist_twist` is `1` or `2` from the CLI's `--wrist-twist` flag; `muscle_use_score` is `0` or `1`, computed by Task 9's temporal analysis and passed in (this module does no time-series analysis itself).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_rula_scoring.py
from tms_vision.angles import JointAngles
from tms_vision.rula.scoring import (
    classify_upper_arm,
    classify_lower_arm,
    classify_wrist,
    classify_neck,
    classify_trunk,
    force_load_score,
    action_level,
    compute_rula_score,
)


def test_classify_upper_arm_neutral_is_score_1():
    assert classify_upper_arm(10.0, shoulder_raised=False, abducted=False, supported=False) == 1


def test_classify_upper_arm_extension_beyond_20_is_score_2():
    assert classify_upper_arm(-25.0, shoulder_raised=False, abducted=False, supported=False) == 2


def test_classify_upper_arm_flexion_90_plus_is_score_4():
    assert classify_upper_arm(95.0, shoulder_raised=False, abducted=False, supported=False) == 4


def test_classify_upper_arm_adjustments_add_up_and_clamp_at_6():
    assert classify_upper_arm(95.0, shoulder_raised=True, abducted=True, supported=False) == 6


def test_classify_upper_arm_supported_subtracts_one():
    assert classify_upper_arm(10.0, shoulder_raised=False, abducted=False, supported=True) == 1


def test_classify_lower_arm_90_degrees_is_score_1():
    assert classify_lower_arm(90.0, across_midline=False) == 1


def test_classify_lower_arm_straight_arm_is_score_2():
    assert classify_lower_arm(175.0, across_midline=False) == 2


def test_classify_wrist_neutral_is_score_1():
    assert classify_wrist(0.5, bent_from_midline=False) == 1


def test_classify_wrist_15_plus_degrees_is_score_3():
    assert classify_wrist(20.0, bent_from_midline=False) == 3


def test_classify_neck_0_to_10_is_score_1():
    assert classify_neck(5.0, twisted=False, side_bending=False) == 1


def test_classify_neck_extension_is_score_4():
    assert classify_neck(-5.0, twisted=False, side_bending=False) == 4


def test_classify_trunk_upright_is_score_1():
    assert classify_trunk(1.0, twisted=False, side_bending=False) == 1


def test_classify_trunk_60_plus_is_score_4():
    assert classify_trunk(70.0, twisted=False, side_bending=False) == 4


def test_force_load_under_2kg_is_score_0():
    assert force_load_score(1.5, is_static_or_repetitive=True) == 0


def test_force_load_2_to_10kg_intermittent_is_score_1():
    assert force_load_score(5.0, is_static_or_repetitive=False) == 1


def test_force_load_2_to_10kg_static_is_score_2():
    assert force_load_score(5.0, is_static_or_repetitive=True) == 2


def test_force_load_over_10kg_is_score_3():
    assert force_load_score(15.0, is_static_or_repetitive=False) == 3


def test_action_level_matches_readme_matrix():
    assert action_level(1) == "acceptable"
    assert action_level(2) == "acceptable"
    assert action_level(3) == "investigation_recommandee"
    assert action_level(4) == "investigation_recommandee"
    assert action_level(5) == "investigation_et_changement_bientot"
    assert action_level(6) == "investigation_et_changement_bientot"
    assert action_level(7) == "changement_immediat"


def _neutral_angles(**overrides):
    base = dict(
        neck_flexion_deg=5.0,
        neck_twisted=False,
        neck_side_bending=False,
        trunk_flexion_deg=1.0,
        trunk_twisted=False,
        trunk_side_bending=False,
        upper_arm_flexion_deg=10.0,
        upper_arm_abducted=False,
        upper_arm_shoulder_raised=False,
        lower_arm_angle_deg=90.0,
        lower_arm_across_midline=False,
        wrist_flexion_deg=0.5,
        wrist_bent_from_midline=False,
        arm_supported=False,
    )
    base.update(overrides)
    return JointAngles(**base)


def test_compute_rula_score_neutral_posture_is_low_risk():
    score = compute_rula_score(
        _neutral_angles(), wrist_twist=1, load_kg=0.0, muscle_use_score=0
    )
    assert score.final_score <= 2
    assert score.action_level == "acceptable"
    assert score.legs == 1


def test_compute_rula_score_high_risk_posture():
    score = compute_rula_score(
        _neutral_angles(
            upper_arm_flexion_deg=95.0,
            upper_arm_abducted=True,
            trunk_flexion_deg=70.0,
            trunk_twisted=True,
            neck_flexion_deg=25.0,
        ),
        wrist_twist=2,
        load_kg=15.0,
        muscle_use_score=1,
    )
    assert score.final_score >= 6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_rula_scoring.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tms_vision.rula.scoring'`

- [ ] **Step 3: Write `src/tms_vision/rula/scoring.py`**

```python
"""Moteur de scoring RULA complet : classification des angles en sous-scores
1-N, puis application des Tables A/B/C officielles (voir rula/tables.py)."""
from dataclasses import dataclass

from tms_vision.angles import JointAngles
from tms_vision.rula.tables import lookup_table_a, lookup_table_b, lookup_table_c

LEGS_SCORE = 1  # Jambes supposées soutenues (limite connue du PoC, voir spec)


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))


def classify_upper_arm(angle_deg: float, shoulder_raised: bool, abducted: bool, supported: bool) -> int:
    if angle_deg < -20.0:
        base = 2
    elif angle_deg <= 20.0:
        base = 1
    elif angle_deg <= 45.0:
        base = 2
    elif angle_deg <= 90.0:
        base = 3
    else:
        base = 4

    score = base + (1 if shoulder_raised else 0) + (1 if abducted else 0) - (1 if supported else 0)
    return _clamp(score, 1, 6)


def classify_lower_arm(angle_deg: float, across_midline: bool) -> int:
    base = 1 if 60.0 <= angle_deg <= 100.0 else 2
    score = base + (1 if across_midline else 0)
    return _clamp(score, 1, 3)


def classify_wrist(flexion_deg: float, bent_from_midline: bool) -> int:
    magnitude = abs(flexion_deg)
    if magnitude <= 2.0:
        base = 1
    elif magnitude <= 15.0:
        base = 2
    else:
        base = 3
    score = base + (1 if bent_from_midline else 0)
    return _clamp(score, 1, 4)


def classify_neck(flexion_deg: float, twisted: bool, side_bending: bool) -> int:
    if flexion_deg < 0:
        base = 4
    elif flexion_deg <= 10.0:
        base = 1
    elif flexion_deg <= 20.0:
        base = 2
    else:
        base = 3

    score = base + (1 if twisted else 0) + (1 if side_bending else 0)
    return _clamp(score, 1, 6)


def classify_trunk(flexion_deg: float, twisted: bool, side_bending: bool) -> int:
    if flexion_deg <= 2.0:
        base = 1
    elif flexion_deg <= 20.0:
        base = 2
    elif flexion_deg <= 60.0:
        base = 3
    else:
        base = 4

    score = base + (1 if twisted else 0) + (1 if side_bending else 0)
    return _clamp(score, 1, 6)


def force_load_score(load_kg: float, is_static_or_repetitive: bool) -> int:
    if load_kg < 2.0:
        return 0
    if load_kg <= 10.0:
        return 2 if is_static_or_repetitive else 1
    return 3


def action_level(final_score: int) -> str:
    if final_score <= 2:
        return "acceptable"
    if final_score <= 4:
        return "investigation_recommandee"
    if final_score <= 6:
        return "investigation_et_changement_bientot"
    return "changement_immediat"


@dataclass
class RulaScore:
    upper_arm: int
    lower_arm: int
    wrist: int
    wrist_twist: int
    posture_score_a: int
    neck: int
    trunk: int
    legs: int
    posture_score_b: int
    muscle_use_score: int
    force_load_score: int
    wrist_arm_score: int
    neck_trunk_leg_score: int
    final_score: int
    action_level: str


def compute_rula_score(
    angles: JointAngles, wrist_twist: int, load_kg: float, muscle_use_score: int
) -> RulaScore:
    upper_arm = classify_upper_arm(
        angles.upper_arm_flexion_deg,
        angles.upper_arm_shoulder_raised,
        angles.upper_arm_abducted,
        angles.arm_supported,
    )
    lower_arm = classify_lower_arm(angles.lower_arm_angle_deg, angles.lower_arm_across_midline)
    wrist = classify_wrist(angles.wrist_flexion_deg, angles.wrist_bent_from_midline)
    neck = classify_neck(angles.neck_flexion_deg, angles.neck_twisted, angles.neck_side_bending)
    trunk = classify_trunk(angles.trunk_flexion_deg, angles.trunk_twisted, angles.trunk_side_bending)

    posture_score_a = lookup_table_a(upper_arm, lower_arm, wrist, wrist_twist)
    posture_score_b = lookup_table_b(neck, trunk, LEGS_SCORE)

    is_static_or_repetitive = muscle_use_score == 1
    force_score = force_load_score(load_kg, is_static_or_repetitive)

    wrist_arm_score = posture_score_a + muscle_use_score + force_score
    neck_trunk_leg_score = posture_score_b + muscle_use_score + force_score

    final_score = lookup_table_c(wrist_arm_score, neck_trunk_leg_score)

    return RulaScore(
        upper_arm=upper_arm,
        lower_arm=lower_arm,
        wrist=wrist,
        wrist_twist=wrist_twist,
        posture_score_a=posture_score_a,
        neck=neck,
        trunk=trunk,
        legs=LEGS_SCORE,
        posture_score_b=posture_score_b,
        muscle_use_score=muscle_use_score,
        force_load_score=force_score,
        wrist_arm_score=wrist_arm_score,
        neck_trunk_leg_score=neck_trunk_leg_score,
        final_score=final_score,
        action_level=action_level(final_score),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_rula_scoring.py -v`
Expected: 20 passed.

- [ ] **Step 5: Write the failing test for the muscle-use temporal heuristic**

```python
# tests/test_rula_scoring.py (append)
from tms_vision.rula.scoring import detect_muscle_use


def test_detect_muscle_use_static_posture_over_one_minute():
    history = [(float(t), 45.0) for t in range(0, 65, 1)]  # angle constant 65s
    assert detect_muscle_use(history) is True


def test_detect_muscle_use_short_clip_with_no_repetition_is_false():
    history = [(float(t), 45.0 + t) for t in range(0, 20, 1)]  # < 1 min, monotonic
    assert detect_muscle_use(history) is False


def test_detect_muscle_use_repetitive_motion_over_4_cycles_per_minute():
    # Oscillation triangulaire : 8 cycles complets sur 60 secondes -> 8/min >= 4/min
    history = []
    for t in range(0, 60):
        phase = t % 7.5
        angle = 20.0 + (20.0 if phase < 3.75 else -20.0)
        history.append((float(t), angle))
    assert detect_muscle_use(history) is True
```

- [ ] **Step 6: Run test to verify it fails**

Run: `venv/bin/pytest tests/test_rula_scoring.py -v -k muscle_use`
Expected: FAIL with `ImportError: cannot import name 'detect_muscle_use'`

- [ ] **Step 7: Add `detect_muscle_use` to `src/tms_vision/rula/scoring.py`**

```python
# Append to src/tms_vision/rula/scoring.py
# (also add `from collections import deque` to the file's imports)

STATIC_DURATION_THRESHOLD_SECONDS = 60.0
STATIC_VARIATION_THRESHOLD_DEG = 15.0
REPETITION_THRESHOLD_PER_MINUTE = 4.0
REPETITION_MIN_PROMINENCE_DEG = 10.0


def _longest_static_span_seconds(history: list[tuple[float, float]]) -> float:
    """Plus longue plage temporelle (en secondes) d'une fenêtre contiguë où
    max(angle) - min(angle) <= STATIC_VARIATION_THRESHOLD_DEG.

    Implémentation O(n) : fenêtre glissante avec deux deques monotones
    (max_deque décroissante, min_deque croissante) maintenant en O(1) amorti
    le max et le min courants de la fenêtre [window_start, end], au lieu de
    reconstruire et scanner la fenêtre à chaque étape (O(n²))."""
    longest = 0.0
    window_start = 0
    max_deque: deque[int] = deque()  # indices, valeurs décroissantes ; tête = max courant
    min_deque: deque[int] = deque()  # indices, valeurs croissantes ; tête = min courant

    for end in range(len(history)):
        angle = history[end][1]

        while max_deque and history[max_deque[-1]][1] <= angle:
            max_deque.pop()
        max_deque.append(end)

        while min_deque and history[min_deque[-1]][1] >= angle:
            min_deque.pop()
        min_deque.append(end)

        while history[max_deque[0]][1] - history[min_deque[0]][1] > STATIC_VARIATION_THRESHOLD_DEG:
            window_start += 1
            if max_deque[0] < window_start:
                max_deque.popleft()
            if min_deque[0] < window_start:
                min_deque.popleft()

        span = history[end][0] - history[window_start][0]
        longest = max(longest, span)
    return longest


def _count_direction_changes(history: list[tuple[float, float]]) -> int:
    changes = 0
    last_extremum = history[0][1]
    direction = 0
    for _, angle in history[1:]:
        delta = angle - last_extremum
        if abs(delta) < REPETITION_MIN_PROMINENCE_DEG:
            continue
        new_direction = 1 if delta > 0 else -1
        if direction != 0 and new_direction != direction:
            changes += 1
        direction = new_direction
        last_extremum = angle
    return changes


def detect_muscle_use(history: list[tuple[float, float]]) -> bool:
    """history : liste de (timestamp_secondes, angle_charge_posturale) triée par temps.
    Retourne True si la posture est majoritairement statique (>1 min sans
    variation significative) ou si le mouvement se répète >= 4 fois/minute."""
    if len(history) < 2:
        return False

    if _longest_static_span_seconds(history) >= STATIC_DURATION_THRESHOLD_SECONDS:
        return True

    duration_minutes = (history[-1][0] - history[0][0]) / 60.0
    if duration_minutes <= 0:
        return False

    direction_changes = _count_direction_changes(history)
    cycles = direction_changes / 2.0
    return (cycles / duration_minutes) >= REPETITION_THRESHOLD_PER_MINUTE
```

- [ ] **Step 8: Run all scoring tests to verify they pass**

Run: `venv/bin/pytest tests/test_rula_scoring.py -v`
Expected: 23 passed.

- [ ] **Step 9: Commit**

```bash
git add src/tms_vision/rula/scoring.py tests/test_rula_scoring.py
git commit -m "feat(tms-vision): add RULA scoring engine with muscle-use temporal heuristic"
```

---

### Task 7: `overlay.py` — skeleton and score badge rendering

**Files:**
- Create: `src/tms_vision/overlay.py`
- Test: `tests/test_overlay.py`

**Interfaces:**
- Consumes: `Landmark` dict from Task 3, `RulaScore` from Task 6, a BGR `np.ndarray` frame.
- Produces:
  - `def action_level_color(action_level: str) -> tuple[int, int, int]` — BGR colour: green/yellow/orange/red matching the README matrix.
  - `def draw_overlay(image_bgr: np.ndarray, landmarks: dict[str, Landmark] | None, score: RulaScore | None) -> np.ndarray` — returns a **new** array (does not mutate the input), draws skeleton connections when `landmarks` is not `None`, and a colored score badge with the final score text when `score` is not `None`. If both are `None`, returns an unmodified copy of the input.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_overlay.py
import numpy as np
from tms_vision.overlay import action_level_color, draw_overlay
from tms_vision.rula.scoring import RulaScore


def _score(final_score, level):
    return RulaScore(
        upper_arm=1, lower_arm=1, wrist=1, wrist_twist=1, posture_score_a=1,
        neck=1, trunk=1, legs=1, posture_score_b=1, muscle_use_score=0,
        force_load_score=0, wrist_arm_score=1, neck_trunk_leg_score=1,
        final_score=final_score, action_level=level,
    )


def test_action_level_color_acceptable_is_green():
    b, g, r = action_level_color("acceptable")
    assert g > r and g > b


def test_action_level_color_immediate_change_is_red():
    b, g, r = action_level_color("changement_immediat")
    assert r > g and r > b


def test_draw_overlay_returns_new_array_without_mutating_input():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    result = draw_overlay(frame, landmarks=None, score=_score(1, "acceptable"))

    assert result is not frame
    assert result.shape == frame.shape
    assert np.any(result != frame)  # le badge a bien été dessiné


def test_draw_overlay_with_no_landmarks_and_no_score_returns_unmodified_copy():
    frame = np.zeros((50, 50, 3), dtype=np.uint8)
    result = draw_overlay(frame, landmarks=None, score=None)

    assert np.array_equal(result, frame)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_overlay.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tms_vision.overlay'`

- [ ] **Step 3: Write `src/tms_vision/overlay.py`**

```python
"""Rendu du squelette et du badge de score RULA sur une frame vidéo."""
import cv2
import numpy as np

from tms_vision.pose_estimation import Landmark
from tms_vision.rula.scoring import RulaScore

_COLOR_BY_LEVEL = {
    "acceptable": (80, 175, 76),  # vert, BGR
    "investigation_recommandee": (60, 210, 235),  # jaune
    "investigation_et_changement_bientot": (40, 150, 235),  # orange
    "changement_immediat": (50, 50, 210),  # rouge
}

_SKELETON_CONNECTIONS = [
    ("LEFT_SHOULDER", "RIGHT_SHOULDER"),
    ("LEFT_SHOULDER", "LEFT_ELBOW"),
    ("LEFT_ELBOW", "LEFT_WRIST"),
    ("RIGHT_SHOULDER", "RIGHT_ELBOW"),
    ("RIGHT_ELBOW", "RIGHT_WRIST"),
    ("LEFT_SHOULDER", "LEFT_HIP"),
    ("RIGHT_SHOULDER", "RIGHT_HIP"),
    ("LEFT_HIP", "RIGHT_HIP"),
    ("LEFT_HIP", "LEFT_KNEE"),
    ("RIGHT_HIP", "RIGHT_KNEE"),
]


def action_level_color(action_level: str) -> tuple[int, int, int]:
    return _COLOR_BY_LEVEL[action_level]


def _draw_skeleton(image: np.ndarray, landmarks: dict[str, Landmark]) -> None:
    height, width = image.shape[:2]
    for start_name, end_name in _SKELETON_CONNECTIONS:
        if start_name not in landmarks or end_name not in landmarks:
            continue
        start = landmarks[start_name]
        end = landmarks[end_name]
        start_point = (int(start.x * width), int(start.y * height))
        end_point = (int(end.x * width), int(end.y * height))
        cv2.line(image, start_point, end_point, (255, 255, 255), 2)
        cv2.circle(image, start_point, 4, (255, 255, 255), -1)
        cv2.circle(image, end_point, 4, (255, 255, 255), -1)


def _draw_score_badge(image: np.ndarray, score: RulaScore) -> None:
    color = action_level_color(score.action_level)
    cv2.rectangle(image, (10, 10), (110, 60), color, -1)
    cv2.putText(
        image,
        f"RULA {score.final_score}",
        (18, 45),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
    )


def draw_overlay(
    image_bgr: np.ndarray, landmarks: dict[str, Landmark] | None, score: RulaScore | None
) -> np.ndarray:
    output = image_bgr.copy()
    if landmarks is not None:
        _draw_skeleton(output, landmarks)
    if score is not None:
        _draw_score_badge(output, score)
    return output
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_overlay.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/tms_vision/overlay.py tests/test_overlay.py
git commit -m "feat(tms-vision): add skeleton and RULA score badge overlay rendering"
```

---

### Task 8: `export.py` — per-frame CSV/JSON export and summary

**Files:**
- Create: `src/tms_vision/export.py`
- Test: `tests/test_export.py`

**Interfaces:**
- Consumes: `JointAngles` (Task 4), `RulaScore` (Task 6).
- Produces:
  - `@dataclass FrameRecord(frame_index: int, timestamp_seconds: float, detected: bool, angles: JointAngles | None, score: RulaScore | None)`
  - `class ResultsExporter: def __init__(self, csv_path: str, summary_json_path: str)`, `def add_frame(self, record: FrameRecord) -> None`, `def finalize(self) -> None` — writes the CSV incrementally is not required; `finalize()` writes both the CSV (one row per `FrameRecord`, `detected=False` rows have empty angle/score columns) and the summary JSON (`{"frame_count": int, "detected_frame_count": int, "max_score": int, "average_score": float, "time_by_action_level": dict[str, float]}`, computed only over detected frames; `average_score`/`max_score` are `0` and `time_by_action_level` is `{}` if no frame was detected).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_export.py
import csv
import json

from tms_vision.angles import JointAngles
from tms_vision.rula.scoring import RulaScore
from tms_vision.export import FrameRecord, ResultsExporter


def _angles():
    return JointAngles(
        neck_flexion_deg=5.0, neck_twisted=False, neck_side_bending=False,
        trunk_flexion_deg=1.0, trunk_twisted=False, trunk_side_bending=False,
        upper_arm_flexion_deg=10.0, upper_arm_abducted=False, upper_arm_shoulder_raised=False,
        lower_arm_angle_deg=90.0, lower_arm_across_midline=False,
        wrist_flexion_deg=0.5, wrist_bent_from_midline=False, arm_supported=False,
    )


def _score(final_score, level):
    return RulaScore(
        upper_arm=1, lower_arm=1, wrist=1, wrist_twist=1, posture_score_a=1,
        neck=1, trunk=1, legs=1, posture_score_b=1, muscle_use_score=0,
        force_load_score=0, wrist_arm_score=1, neck_trunk_leg_score=1,
        final_score=final_score, action_level=level,
    )


def test_export_writes_csv_row_per_frame_and_summary_json(tmp_path):
    csv_path = tmp_path / "frames.csv"
    summary_path = tmp_path / "summary.json"
    exporter = ResultsExporter(str(csv_path), str(summary_path))

    exporter.add_frame(FrameRecord(0, 0.0, True, _angles(), _score(1, "acceptable")))
    exporter.add_frame(FrameRecord(1, 1.0, True, _angles(), _score(7, "changement_immediat")))
    exporter.add_frame(FrameRecord(2, 2.0, False, None, None))
    exporter.finalize()

    with open(csv_path, newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3
    assert rows[0]["detected"] == "True"
    assert rows[0]["final_score"] == "1"
    assert rows[2]["detected"] == "False"
    assert rows[2]["final_score"] == ""

    with open(summary_path) as f:
        summary = json.load(f)
    assert summary["frame_count"] == 3
    assert summary["detected_frame_count"] == 2
    assert summary["max_score"] == 7
    assert summary["average_score"] == 4.0
    assert summary["time_by_action_level"]["acceptable"] == 1.0
    assert summary["time_by_action_level"]["changement_immediat"] == 1.0


def test_export_with_no_detected_frames_gives_zeroed_summary(tmp_path):
    csv_path = tmp_path / "frames.csv"
    summary_path = tmp_path / "summary.json"
    exporter = ResultsExporter(str(csv_path), str(summary_path))
    exporter.add_frame(FrameRecord(0, 0.0, False, None, None))
    exporter.finalize()

    with open(summary_path) as f:
        summary = json.load(f)
    assert summary["max_score"] == 0
    assert summary["average_score"] == 0
    assert summary["time_by_action_level"] == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_export.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tms_vision.export'`

- [ ] **Step 3: Write `src/tms_vision/export.py`**

```python
"""Export CSV par frame et résumé JSON de fin d'analyse."""
import csv
import json
from dataclasses import dataclass

from tms_vision.angles import JointAngles
from tms_vision.rula.scoring import RulaScore

CSV_FIELDS = [
    "frame_index", "timestamp_seconds", "detected",
    "neck_flexion_deg", "trunk_flexion_deg", "upper_arm_flexion_deg",
    "lower_arm_angle_deg", "wrist_flexion_deg",
    "upper_arm", "lower_arm", "wrist", "neck", "trunk", "legs",
    "muscle_use_score", "force_load_score", "final_score", "action_level",
]


@dataclass
class FrameRecord:
    frame_index: int
    timestamp_seconds: float
    detected: bool
    angles: JointAngles | None
    score: RulaScore | None


class ResultsExporter:
    def __init__(self, csv_path: str, summary_json_path: str):
        self._csv_path = csv_path
        self._summary_json_path = summary_json_path
        self._records: list[FrameRecord] = []

    def add_frame(self, record: FrameRecord) -> None:
        self._records.append(record)

    def _row_for(self, record: FrameRecord) -> dict:
        row = {field: "" for field in CSV_FIELDS}
        row["frame_index"] = record.frame_index
        row["timestamp_seconds"] = record.timestamp_seconds
        row["detected"] = record.detected
        if record.angles is not None:
            row["neck_flexion_deg"] = record.angles.neck_flexion_deg
            row["trunk_flexion_deg"] = record.angles.trunk_flexion_deg
            row["upper_arm_flexion_deg"] = record.angles.upper_arm_flexion_deg
            row["lower_arm_angle_deg"] = record.angles.lower_arm_angle_deg
            row["wrist_flexion_deg"] = record.angles.wrist_flexion_deg
        if record.score is not None:
            row["upper_arm"] = record.score.upper_arm
            row["lower_arm"] = record.score.lower_arm
            row["wrist"] = record.score.wrist
            row["neck"] = record.score.neck
            row["trunk"] = record.score.trunk
            row["legs"] = record.score.legs
            row["muscle_use_score"] = record.score.muscle_use_score
            row["force_load_score"] = record.score.force_load_score
            row["final_score"] = record.score.final_score
            row["action_level"] = record.score.action_level
        return row

    def _summary(self) -> dict:
        detected = [r for r in self._records if r.detected and r.score is not None]
        if not detected:
            return {
                "frame_count": len(self._records),
                "detected_frame_count": 0,
                "max_score": 0,
                "average_score": 0,
                "time_by_action_level": {},
            }

        scores = [r.score.final_score for r in detected]
        time_by_level: dict[str, float] = {}
        for record in detected:
            # Cherche le prochain frame (détecté ou non) dans self._records :
            # regarder uniquement les frames détectées sous-estime la durée
            # quand des frames non détectées s'intercalent entre deux détections.
            next_timestamp = None
            for r in self._records:
                if r.frame_index > record.frame_index:
                    next_timestamp = r.timestamp_seconds
                    break

            if next_timestamp is None:
                duration = 1.0 if len(detected) == 1 else 0.0
            else:
                duration = max(next_timestamp - record.timestamp_seconds, 0.0) or (
                    1.0 if len(detected) == 1 else 0.0
                )

            time_by_level[record.score.action_level] = (
                time_by_level.get(record.score.action_level, 0.0) + duration
            )

        return {
            "frame_count": len(self._records),
            "detected_frame_count": len(detected),
            "max_score": max(scores),
            "average_score": sum(scores) / len(scores),
            "time_by_action_level": time_by_level,
        }

    def finalize(self) -> None:
        with open(self._csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for record in self._records:
                writer.writerow(self._row_for(record))

        with open(self._summary_json_path, "w") as f:
            json.dump(self._summary(), f, indent=2, ensure_ascii=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_export.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/tms_vision/export.py tests/test_export.py
git commit -m "feat(tms-vision): add per-frame CSV export and analysis summary JSON"
```

---

### Task 9: `cli.py` — orchestration entrypoint

**Files:**
- Create: `src/tms_vision/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `FrameSource` (Task 2), `PoseEstimator`/`PoseResult` (Task 3), `compute_joint_angles` (Task 4), `compute_rula_score`/`detect_muscle_use` (Task 6), `draw_overlay` (Task 7), `FrameRecord`/`ResultsExporter` (Task 8).
- Produces:
  - `def parse_args(argv: list[str]) -> argparse.Namespace` — flags: `--source` (required, `"webcam"` or a file path), `--side` (`"left"`|`"right"`, default `"right"`), `--load-kg` (float, default `0.0`, must be `>= 0`), `--wrist-twist` (`"normal"`|`"extreme"`, default `"normal"`), `--output-dir` (default `"outputs"`).
  - `def run(args: argparse.Namespace) -> None` — orchestrates the full pipeline: opens `FrameSource`, runs `PoseEstimator` per frame, computes angles, accumulates a `(timestamp, trunk_flexion+upper_arm_flexion)` history for `detect_muscle_use`, computes `RulaScore` per frame using the **clip-wide** muscle-use result (computed once after a first pass, since it needs the whole time series), writes an annotated video via `cv2.VideoWriter`, and calls `ResultsExporter.finalize()`.
  - `def main() -> None` — entrypoint calling `parse_args(sys.argv[1:])` then `run(...)`, with `try/except` around `FileNotFoundError`/`RuntimeError` from `FrameSource` printing a clear French error message to stderr and exiting with code 1.

- [ ] **Step 1: Write the failing tests for argument parsing and validation**

```python
# tests/test_cli.py
import pytest
from tms_vision.cli import parse_args


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tms_vision.cli'`

- [ ] **Step 3: Write `src/tms_vision/cli.py`**

```python
"""Point d'entrée CLI : orchestre capture -> pose -> angles -> score RULA ->
overlay vidéo + export CSV/JSON.

Conseil de prise de vue : pour des angles fiables (flexion/extension du cou,
du tronc et du bras), filmer la personne DE PROFIL plutôt que de face.
"""
import argparse
import sys
import time
from pathlib import Path

import cv2

from tms_vision.capture import FrameSource
from tms_vision.pose_estimation import PoseEstimator
from tms_vision.angles import compute_joint_angles
from tms_vision.rula.scoring import compute_rula_score, detect_muscle_use
from tms_vision.overlay import draw_overlay
from tms_vision.export import FrameRecord, ResultsExporter


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
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = time.strftime("%Y%m%d-%H%M%S")

    wrist_twist = 1 if args.wrist_twist == "normal" else 2

    source = FrameSource(args.source)
    estimator = PoseEstimator()

    frames = list(source)
    source.release()

    per_frame_angles = []
    posture_load_history: list[tuple[float, float]] = []

    for frame in frames:
        pose_result = estimator.process(frame.image)
        angles = None
        if pose_result.landmarks is not None:
            angles = compute_joint_angles(pose_result.landmarks, side=args.side)
        per_frame_angles.append((frame, pose_result, angles))
        if angles is not None:
            posture_load = angles.trunk_flexion_deg + angles.upper_arm_flexion_deg
            posture_load_history.append((frame.timestamp_seconds, posture_load))

    estimator.close()

    muscle_use_score = 1 if detect_muscle_use(posture_load_history) else 0

    height, width = frames[0].image.shape[:2] if frames else (0, 0)
    video_path = output_dir / f"{run_id}_annotated.mp4"
    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), source.fps() or 30.0, (width, height)
    )

    exporter = ResultsExporter(
        str(output_dir / f"{run_id}_frames.csv"),
        str(output_dir / f"{run_id}_summary.json"),
    )

    for frame, pose_result, angles in per_frame_angles:
        score = None
        if angles is not None:
            score = compute_rula_score(
                angles, wrist_twist=wrist_twist, load_kg=args.load_kg, muscle_use_score=muscle_use_score
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
    print(f"Vidéo annotée : {video_path}")
    print(f"Export CSV/JSON : {output_dir}/{run_id}_frames.csv, {output_dir}/{run_id}_summary.json")


def main() -> None:
    args = parse_args(sys.argv[1:])
    try:
        run(args)
    except (FileNotFoundError, RuntimeError) as error:
        print(f"Erreur : {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_cli.py -v`
Expected: 4 passed.

- [ ] **Step 5: Write the failing integration test using a synthetic video**

```python
# tests/test_cli.py (append)
import numpy as np
import cv2

from tms_vision.cli import parse_args, run


def test_run_end_to_end_on_a_blank_synthetic_video(tmp_path):
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

    csv_files = list(output_dir.glob("*_frames.csv"))
    summary_files = list(output_dir.glob("*_summary.json"))
    video_files = list(output_dir.glob("*_annotated.mp4"))
    assert len(csv_files) == 1
    assert len(summary_files) == 1
    assert len(video_files) == 1
```

- [ ] **Step 6: Run test to verify it fails, then re-run after Step 3's code (already written) to confirm it passes**

Run: `venv/bin/pytest tests/test_cli.py -v`
Expected: 5 passed. (No implementation change needed here — this test validates the orchestration already written in Step 3 end-to-end against a blank synthetic video, where no pose will be detected, exercising the `detected=False` path through the whole pipeline.)

- [ ] **Step 7: Commit**

```bash
git add src/tms_vision/cli.py tests/test_cli.py
git commit -m "feat(tms-vision): add CLI orchestration for the full pose-to-RULA pipeline"
```

---

### Task 10: Manual end-to-end verification with the webcam

**Files:**
- Modify: `README.md` (add a "Lancer le PoC" usage section)

**Interfaces:**
- Consumes: the finished `tms_vision.cli` entrypoint from Task 9.
- Produces: no new code — this task is a manual smoke test plus documentation, closing out the PoC.

- [ ] **Step 1: Run the full test suite one final time**

Run: `venv/bin/pytest -v`
Expected: all tests from Tasks 2-9 pass (48 passed: 2 capture + 1 pose_estimation + 4 angles + 7 rula/tables + 23 rula/scoring + 4 overlay + 2 export + 5 cli).

- [ ] **Step 2: Run the pipeline live against the webcam for a short clip**

Run: `venv/bin/python -m tms_vision.cli --source webcam --side right --load-kg 0 --output-dir outputs`
(Let it run for ~15-20 seconds, then stop it with Ctrl+C — note: Ctrl+C during the capture loop will not currently flush partial output, since `run()` reads all frames into memory before processing. For this manual check, prefer recording a short file first with e.g. QuickTime and passing `--source path/to/clip.mov`.)

Expected: `outputs/<run_id>_annotated.mp4`, `outputs/<run_id>_frames.csv`, `outputs/<run_id>_summary.json` are created; opening the annotated video shows the skeleton overlay and a colored RULA score badge; the CSV has one row per frame with non-empty angle/score columns while a person is visible.

- [ ] **Step 3: Add a "Lancer le PoC" section to `README.md`**

Add after the "8. Feuille de Route de Déploiement" section:

```markdown
## 9. Lancer le PoC (Phase 1)

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/pytest                                    # suite de tests

venv/bin/python -m tms_vision.cli \
  --source chemin/vers/video.mp4 \
  --side right \
  --load-kg 2.5 \
  --wrist-twist normal \
  --output-dir outputs
```

**Conseil de prise de vue** : filmer la personne de profil pour des angles de flexion/extension fiables (cou, tronc, bras).

Résultats dans `outputs/` : une vidéo annotée (squelette + badge de score RULA coloré), un CSV détaillé par frame, et un résumé JSON (score max, score moyen, temps passé par niveau de risque).
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs(tms-vision): document how to run the Phase 1 PoC pipeline"
```

---

## Self-Review Notes

- **Spec coverage:** venv Python 3.11 (Task 1) · capture webcam/vidéo (Task 2) · MediaPipe Pose (Task 3) · calcul d'angles (Task 4) · RULA complet Tables A/B/C (Tasks 5-6) · usage musculaire automatique (Task 6) · force/torsion manuels (Task 6, 9) · jambes fixées à 1 (Task 6) · overlay vidéo + export CSV/JSON (Tasks 7-8) · gestion d'erreurs webcam/fichier/paramètres (Tasks 2, 9) · tests angles/tables (Tasks 4, 5). All spec sections are covered.
- **Type consistency checked:** `JointAngles` field names are identical across Task 4 (definition), Task 6 (`compute_rula_score` consumption), Task 8 (`FrameRecord`/CSV), Task 9 (posture-load history). `RulaScore` field names are identical across Task 6 (definition), Task 7 (overlay), Task 8 (export). `Landmark`/`PoseResult` are identical across Task 3 (definition), Task 4, Task 7, Task 9.
- **No placeholders:** every task contains complete, runnable code; the two intentionally-simplified fields (`wrist_bent_from_midline`, `arm_supported`) are hardcoded `False` with an inline comment naming the concrete monocular-vision limitation, not a `TODO`.
