# Avatar 3D de posture — Tranche 1 (mannequin piloté par la pose) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exporter la pose 3D (`pose_world_landmarks` de MediaPipe) calculée pendant l'analyse existante, et l'utiliser côté navigateur pour animer un mannequin 3D (capsules) en synchro avec la lecture de la vidéo annotée, avec une caméra orientable.

**Architecture:** Backend Python (déjà en place) : `PoseEstimator` expose en plus les landmarks 3D à l'échelle métrique ; `analyze_video()` les lisse temporellement et les écrit dans un nouveau fichier `{run_id}_pose3d.json`, aux côtés des exports CSV/JSON existants, servi par l'endpoint générique `GET /outputs/{filename}` déjà en place. Frontend Next.js : un nouveau composant `PostureAvatar3D` (react-three-fiber) charge ce JSON une fois l'analyse terminée, et anime un rig de capsules en lisant en continu `video.currentTime` de l'élément `<video>` existant.

**Tech Stack:** Python/MediaPipe/OpenCV (existant), FastAPI (existant), Next.js/React/TypeScript (existant) + `three`, `@react-three/fiber`, `@react-three/drei` (nouveaux).

## Global Constraints

- Rejoué après analyse (pas de mode miroir en direct) — voir spec, section "Décisions de cadrage".
- Rendu 3D dans le navigateur (Three.js), pas de rendu headless côté serveur.
- Caméra orientable par l'utilisateur (OrbitControls), pas fixe.
- Rig = exactement les mêmes segments que `overlay.py::_SKELETON_CONNECTIONS` (10 connexions) + une sphère tête sur `NOSE`. Pas de mains/doigts, pas de jambes sous le genou.
- Couleur : tout l'avatar prend la couleur du niveau d'action RULA global de la frame courante (pas de coloration par segment dans cette tranche).
- Pose figée (dernière pose connue) pendant les frames sans détection, côté navigateur.
- Pas de nouveau fichier `.md`/doc hors ce plan et le spec déjà commité.
- Spec de référence : `docs/superpowers/specs/2026-09-16-3d-posture-avatar-design.md`.

---

## Task 1: `pose_estimation.py` — exposer les landmarks 3D (`world_landmarks`)

**Files:**
- Modify: `src/tms_vision/pose_estimation.py`
- Test: `tests/test_pose_estimation.py`

**Interfaces:**
- Consumes: rien de nouveau (MediaPipe `results.pose_world_landmarks`, déjà fourni par le modèle déjà utilisé).
- Produces: `PoseResult.world_landmarks: dict[str, Landmark] | None`, peuplé avec les mêmes clés (noms de landmarks) que `PoseResult.landmarks` quand une pose est détectée, `None` sinon. Utilisé par le Task 3.

- [ ] **Step 1: Écrire le test qui échoue**

Dans `tests/test_pose_estimation.py`, ajouter :

```python
def test_blank_frame_returns_no_world_landmarks():
    estimator = PoseEstimator()
    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    result = estimator.process(blank)
    estimator.close()

    assert result.world_landmarks is None
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `venv/bin/pytest tests/test_pose_estimation.py -v`
Expected: FAIL avec `AttributeError: 'PoseResult' object has no attribute 'world_landmarks'`

- [ ] **Step 3: Implémenter**

Dans `src/tms_vision/pose_estimation.py`, remplacer le bloc `PoseResult` et `process()` :

```python
@dataclass
class PoseResult:
    landmarks: dict[str, Landmark] | None
    world_landmarks: dict[str, Landmark] | None = None
```

```python
    def process(self, image_bgr: np.ndarray) -> PoseResult:
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        results = self._pose.process(image_rgb)

        if results.pose_landmarks is None:
            return PoseResult(landmarks=None, world_landmarks=None)

        landmarks: dict[str, Landmark] = {}
        world_landmarks: dict[str, Landmark] = {}
        pose_landmark_enum = mp.solutions.pose.PoseLandmark
        for landmark_id, raw in enumerate(results.pose_landmarks.landmark):
            if raw.visibility < self._min_visibility:
                continue
            name = pose_landmark_enum(landmark_id).name
            landmarks[name] = Landmark(
                x=raw.x, y=raw.y, z=raw.z, visibility=raw.visibility
            )
            if results.pose_world_landmarks is not None:
                raw_world = results.pose_world_landmarks.landmark[landmark_id]
                world_landmarks[name] = Landmark(
                    x=raw_world.x, y=raw_world.y, z=raw_world.z, visibility=raw_world.visibility
                )

        return PoseResult(
            landmarks=landmarks or None,
            world_landmarks=world_landmarks or None,
        )
```

(Le filtre de visibilité réutilise `raw.visibility`, celui du landmark 2D, pour garder exactement le même jeu de clés entre `landmarks` et `world_landmarks` — nécessaire pour le Task 3 qui les associe par nom.)

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `venv/bin/pytest tests/test_pose_estimation.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tms_vision/pose_estimation.py tests/test_pose_estimation.py
git commit -m "feat: expose les landmarks 3D MediaPipe (world_landmarks) sur PoseResult"
```

---

## Task 2: `pose3d_export.py` — lissage temporel et export JSON (nouveau module)

**Files:**
- Create: `src/tms_vision/pose3d_export.py`
- Test: `tests/test_pose3d_export.py`

**Interfaces:**
- Consumes: `tms_vision.pose_estimation.Landmark` (Task 1, déjà existant).
- Produces:
  - `Pose3DFrameRecord(frame_index: int, timestamp_seconds: float, detected: bool, landmarks: dict[str, Landmark] | None, action_level: str | None)` (dataclass)
  - `smooth_world_landmarks(frames: list[dict[str, Landmark] | None], window: int = 5) -> list[dict[str, Landmark] | None]`
  - `write_pose3d_json(path: str, records: list[Pose3DFrameRecord]) -> None`
  Utilisés par le Task 3.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_pose3d_export.py` :

```python
import json
import random

import pytest

from tms_vision.pose_estimation import Landmark
from tms_vision.pose3d_export import Pose3DFrameRecord, smooth_world_landmarks, write_pose3d_json


def test_smooth_world_landmarks_keeps_constant_sequence_unchanged():
    frame = {"NOSE": Landmark(x=1.0, y=2.0, z=3.0, visibility=0.9)}
    frames = [frame, frame, frame, frame, frame]

    smoothed = smooth_world_landmarks(frames, window=5)

    for result in smoothed:
        assert result["NOSE"].x == pytest.approx(1.0)
        assert result["NOSE"].y == pytest.approx(2.0)
        assert result["NOSE"].z == pytest.approx(3.0)


def test_smooth_world_landmarks_keeps_none_frames_none():
    detected = {"NOSE": Landmark(x=0.0, y=0.0, z=0.0, visibility=0.9)}
    frames = [detected, None, detected]

    smoothed = smooth_world_landmarks(frames, window=3)

    assert smoothed[1] is None
    assert smoothed[0] is not None
    assert smoothed[2] is not None


def test_smooth_world_landmarks_reduces_noise_variance():
    random.seed(0)
    raw_xs = [1.0 + random.uniform(-0.1, 0.1) for _ in range(20)]
    frames = [{"NOSE": Landmark(x=x, y=0.0, z=0.0, visibility=0.9)} for x in raw_xs]

    smoothed = smooth_world_landmarks(frames, window=5)
    smoothed_xs = [f["NOSE"].x for f in smoothed]

    def variance(values):
        mean = sum(values) / len(values)
        return sum((v - mean) ** 2 for v in values) / len(values)

    assert variance(smoothed_xs) < variance(raw_xs)


def test_write_pose3d_json_writes_one_entry_per_frame(tmp_path):
    path = tmp_path / "pose3d.json"
    records = [
        Pose3DFrameRecord(0, 0.0, True, {"NOSE": Landmark(0.1, 0.2, 0.3, 0.9)}, "acceptable"),
        Pose3DFrameRecord(1, 1.0, False, None, None),
    ]

    write_pose3d_json(str(path), records)

    data = json.loads(path.read_text())
    assert len(data) == 2
    assert data[0]["frame_index"] == 0
    assert data[0]["detected"] is True
    assert data[0]["landmarks"]["NOSE"] == [0.1, 0.2, 0.3]
    assert data[0]["action_level"] == "acceptable"
    assert data[1]["landmarks"] is None
    assert data[1]["action_level"] is None
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `venv/bin/pytest tests/test_pose3d_export.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'tms_vision.pose3d_export'`

- [ ] **Step 3: Implémenter**

Créer `src/tms_vision/pose3d_export.py` :

```python
"""Lissage temporel et export JSON de la trajectoire 3D de pose
(pose_world_landmarks de MediaPipe), pour piloter l'avatar 3D côté
navigateur (voir docs/superpowers/specs/2026-09-16-3d-posture-avatar-design.md).
"""
import json
from dataclasses import dataclass

from tms_vision.pose_estimation import Landmark

SMOOTHING_WINDOW = 5  # frames, fenêtre centrée


@dataclass
class Pose3DFrameRecord:
    frame_index: int
    timestamp_seconds: float
    detected: bool
    landmarks: dict[str, Landmark] | None
    action_level: str | None


def smooth_world_landmarks(
    frames: list[dict[str, Landmark] | None], window: int = SMOOTHING_WINDOW
) -> list[dict[str, Landmark] | None]:
    """Moyenne glissante centrée par landmark, sur toute la séquence (pas de
    contrainte temps réel ici). Une frame sans détection (None) reste None
    en sortie -- pas d'invention de pose là où MediaPipe n'en a pas trouvé."""
    half = window // 2
    smoothed: list[dict[str, Landmark] | None] = []

    for i, frame in enumerate(frames):
        if frame is None:
            smoothed.append(None)
            continue

        neighbors = [
            frames[j]
            for j in range(max(0, i - half), min(len(frames), i + half + 1))
            if frames[j] is not None
        ]

        averaged: dict[str, Landmark] = {}
        for name, landmark in frame.items():
            samples = [neighbor[name] for neighbor in neighbors if name in neighbor]
            averaged[name] = Landmark(
                x=sum(sample.x for sample in samples) / len(samples),
                y=sum(sample.y for sample in samples) / len(samples),
                z=sum(sample.z for sample in samples) / len(samples),
                visibility=landmark.visibility,
            )
        smoothed.append(averaged)

    return smoothed


def write_pose3d_json(path: str, records: list[Pose3DFrameRecord]) -> None:
    payload = []
    for record in records:
        landmarks = None
        if record.landmarks is not None:
            landmarks = {
                name: [landmark.x, landmark.y, landmark.z]
                for name, landmark in record.landmarks.items()
            }
        payload.append(
            {
                "frame_index": record.frame_index,
                "timestamp_seconds": record.timestamp_seconds,
                "detected": record.detected,
                "landmarks": landmarks,
                "action_level": record.action_level,
            }
        )
    with open(path, "w") as f:
        json.dump(payload, f, ensure_ascii=False)
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `venv/bin/pytest tests/test_pose3d_export.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tms_vision/pose3d_export.py tests/test_pose3d_export.py
git commit -m "feat: lissage temporel et export JSON de la trajectoire de pose 3D"
```

---

## Task 3: `pipeline.py` — brancher l'export pose 3D dans `analyze_video()`

**Files:**
- Modify: `src/tms_vision/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `PoseResult.world_landmarks` (Task 1), `Pose3DFrameRecord`/`smooth_world_landmarks`/`write_pose3d_json` (Task 2).
- Produces: `AnalysisResult.pose3d_path: Path | None`, fichier `{run_id}_pose3d.json` dans le dossier de sortie. Utilisé par le Task 4.

- [ ] **Step 1: Écrire le test qui échoue**

Dans `tests/test_pipeline.py`, ajouter en haut du fichier `import json` (pas encore importé), puis ajouter ce test :

```python
def test_analyze_video_produces_pose3d_json(tmp_path):
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

    assert result.pose3d_path is not None
    assert result.pose3d_path.exists()
    data = json.loads(result.pose3d_path.read_text())
    assert len(data) == 3
    for entry in data:
        assert entry["detected"] is False
        assert entry["landmarks"] is None
        assert entry["action_level"] is None
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `venv/bin/pytest tests/test_pipeline.py::test_analyze_video_produces_pose3d_json -v`
Expected: FAIL avec `AttributeError: 'AnalysisResult' object has no attribute 'pose3d_path'`

- [ ] **Step 3: Implémenter**

Dans `src/tms_vision/pipeline.py`, ajouter l'import (avec les autres imports de `tms_vision`) :

```python
from tms_vision.pose3d_export import Pose3DFrameRecord, smooth_world_landmarks, write_pose3d_json
```

Modifier `AnalysisResult` :

```python
@dataclass
class AnalysisResult:
    empty: bool
    video_path: Path | None = None
    csv_path: Path | None = None
    summary_json_path: Path | None = None
    pose3d_path: Path | None = None
```

Remplacer le bloc allant de la création de `csv_path`/`summary_json_path`/`exporter` jusqu'au `return` final par :

```python
    csv_path = output_path / f"{run_id}_frames.csv"
    summary_json_path = output_path / f"{run_id}_summary.json"
    pose3d_path = output_path / f"{run_id}_pose3d.json"
    exporter = ResultsExporter(str(csv_path), str(summary_json_path))

    raw_world_landmarks = [pose_result.world_landmarks for _, pose_result, _ in per_frame_angles]
    smoothed_world_landmarks = smooth_world_landmarks(raw_world_landmarks)
    pose3d_records: list[Pose3DFrameRecord] = []

    for (frame, pose_result, angles), world_landmarks in zip(per_frame_angles, smoothed_world_landmarks):
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
        pose3d_records.append(
            Pose3DFrameRecord(
                frame_index=frame.index,
                timestamp_seconds=frame.timestamp_seconds,
                detected=angles is not None,
                landmarks=world_landmarks,
                action_level=score.action_level if score is not None else None,
            )
        )

    writer.release()
    exporter.finalize()
    write_pose3d_json(str(pose3d_path), pose3d_records)

    return AnalysisResult(
        empty=False, video_path=video_path, csv_path=csv_path, summary_json_path=summary_json_path,
        pose3d_path=pose3d_path,
    )
```

- [ ] **Step 4: Lancer tous les tests du pipeline pour vérifier qu'ils passent**

Run: `venv/bin/pytest tests/test_pipeline.py -v`
Expected: PASS (tous les tests, y compris les préexistants et le nouveau)

- [ ] **Step 5: Lancer la suite complète pour vérifier l'absence de régression**

Run: `venv/bin/pytest -v`
Expected: PASS (tous les tests)

- [ ] **Step 6: Commit**

```bash
git add src/tms_vision/pipeline.py tests/test_pipeline.py
git commit -m "feat: analyze_video exporte la trajectoire de pose 3D lissée (pose3d.json)"
```

---

## Task 4: `api.py` — exposer `pose3d_url` dans la réponse

**Files:**
- Modify: `src/tms_vision/api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `AnalysisResult.pose3d_path` (Task 3).
- Produces: le JSON de réponse de `POST /analyses` et `POST /uploads/{id}/complete` gagne un champ `"pose3d_url": "/outputs/{run_id}_pose3d.json"`. Consommé par le Task 7 (frontend).

- [ ] **Step 1: Modifier les tests existants pour vérifier le nouveau champ**

Dans `tests/test_api.py`, dans `test_create_analysis_with_no_detectable_person_returns_empty_summary`, ajouter après la ligne `assert body["csv_url"].startswith("/outputs/")` :

```python
    assert body["pose3d_url"].startswith("/outputs/")
```

Dans `test_output_files_are_actually_served_at_returned_urls`, ajouter après le bloc `csv_response` existant :

```python
    pose3d_response = client.get(body["pose3d_url"])
    assert pose3d_response.status_code == 200
    assert len(pose3d_response.content) > 0
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `venv/bin/pytest tests/test_api.py::test_create_analysis_with_no_detectable_person_returns_empty_summary tests/test_api.py::test_output_files_are_actually_served_at_returned_urls -v`
Expected: FAIL avec `KeyError: 'pose3d_url'`

- [ ] **Step 3: Implémenter**

Dans `src/tms_vision/api.py`, dans `_analyze_and_build_response`, remplacer :

```python
    summary = json.loads(result.summary_json_path.read_text())
    return {
        "summary": summary,
        "annotated_video_url": f"/outputs/{result.video_path.name}",
        "csv_url": f"/outputs/{result.csv_path.name}",
    }
```

par :

```python
    summary = json.loads(result.summary_json_path.read_text())
    return {
        "summary": summary,
        "annotated_video_url": f"/outputs/{result.video_path.name}",
        "csv_url": f"/outputs/{result.csv_path.name}",
        "pose3d_url": f"/outputs/{result.pose3d_path.name}",
    }
```

- [ ] **Step 4: Lancer toute la suite pour vérifier l'absence de régression**

Run: `venv/bin/pytest -v`
Expected: PASS (tous les tests)

- [ ] **Step 5: Commit**

```bash
git add src/tms_vision/api.py tests/test_api.py
git commit -m "feat: expose pose3d_url dans la réponse de /analyses et /uploads/.../complete"
```

---

## Task 5: Dépendances frontend — three.js / react-three-fiber / drei

**Files:**
- Modify: `web/package.json`

**Interfaces:**
- Consumes: rien.
- Produces: `three@0.186.0`, `@react-three/fiber@9.7.0`, `@react-three/drei@10.7.8`, `@types/three@0.186.0` installés dans `web/node_modules`. Utilisés par le Task 6.

Ces versions sont vérifiées compatibles entre elles et avec la stack existante (`react@19.2.8`,
`react-dom@19.2.8`, déjà dans `web/package.json`) : `@react-three/fiber@9.7.0` déclare
`peerDependencies` `react: ">=19 <19.3"` / `three: ">=0.156"` ; `@react-three/drei@10.7.8` déclare
`react: "^19"` / `@react-three/fiber: "^9.0.0"` / `three: ">=0.159"`.

- [ ] **Step 1: Ajouter les dépendances**

Run (depuis `web/`) :

```bash
cd web && npm install three@0.186.0 @react-three/fiber@9.7.0 @react-three/drei@10.7.8
npm install --save-dev @types/three@0.186.0
```

- [ ] **Step 2: Vérifier l'installation**

Run: `cd web && npm run build`
Expected: le build Next.js réussit (aucun import n'utilise encore ces packages à ce stade, donc pas d'erreur de compilation liée à eux — cette étape vérifie seulement qu'`npm install` n'a pas cassé le projet).

- [ ] **Step 3: Commit**

```bash
git add web/package.json web/package-lock.json
git commit -m "chore: ajoute three.js/react-three-fiber/drei pour l'avatar 3D de posture"
```

---

## Task 6: `PostureAvatar3D.tsx` — composant de rendu 3D

**Files:**
- Create: `web/app/PostureAvatar3D.tsx`

**Interfaces:**
- Consumes: `pose3dUrl: string` (vient de `result.pose3d_url`, Task 4), `videoRef: React.RefObject<HTMLVideoElement | null>` (vient de Task 7).
- Produces: `export function PostureAvatar3D({ pose3dUrl, videoRef }): JSX.Element`. Utilisé par le Task 7.

- [ ] **Step 1: Créer le composant**

Créer `web/app/PostureAvatar3D.tsx` :

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { Canvas, useFrame } from "@react-three/fiber";
import { Capsule, OrbitControls, Sphere } from "@react-three/drei";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Mêmes segments que src/tms_vision/overlay.py::_SKELETON_CONNECTIONS.
const SKELETON_CONNECTIONS: [string, string][] = [
  ["LEFT_SHOULDER", "RIGHT_SHOULDER"],
  ["LEFT_SHOULDER", "LEFT_ELBOW"],
  ["LEFT_ELBOW", "LEFT_WRIST"],
  ["RIGHT_SHOULDER", "RIGHT_ELBOW"],
  ["RIGHT_ELBOW", "RIGHT_WRIST"],
  ["LEFT_SHOULDER", "LEFT_HIP"],
  ["RIGHT_SHOULDER", "RIGHT_HIP"],
  ["LEFT_HIP", "RIGHT_HIP"],
  ["LEFT_HIP", "LEFT_KNEE"],
  ["RIGHT_HIP", "RIGHT_KNEE"],
];
const HEAD_LANDMARK = "NOSE";
const CAPSULE_RADIUS = 0.05;
const HEAD_RADIUS = 0.12;

// Même palette que src/tms_vision/overlay.py::_COLOR_BY_LEVEL (converti BGR -> hex RGB).
const ACTION_LEVEL_COLORS: Record<string, string> = {
  acceptable: "#4CAF50",
  investigation_recommandee: "#EBD23C",
  investigation_et_changement_bientot: "#EB9628",
  changement_immediat: "#D23232",
};
const DEFAULT_COLOR = "#9E9E9E";

type Pose3DLandmarks = Record<string, [number, number, number]>;

type Pose3DFrame = {
  frame_index: number;
  timestamp_seconds: number;
  detected: boolean;
  landmarks: Pose3DLandmarks | null;
  action_level: string | null;
};

function toThreeVector(coords: [number, number, number]): THREE.Vector3 {
  const [x, y, z] = coords;
  // MediaPipe pose_world_landmarks : x droite, y vers le bas (même
  // orientation que les landmarks 2D image), origine au centre des
  // hanches. Three.js est y-vers-le-haut : on inverse y. À vérifier
  // visuellement sur une vraie vidéo (Task 8) -- inverser un autre axe ici
  // si l'avatar apparaît miroir ou de travers.
  return new THREE.Vector3(x, -y, z);
}

function findNearestFrameIndex(frames: Pose3DFrame[], time: number): number {
  let low = 0;
  let high = frames.length - 1;
  while (low < high) {
    const mid = (low + high) >> 1;
    if (frames[mid].timestamp_seconds < time) {
      low = mid + 1;
    } else {
      high = mid;
    }
  }
  if (
    low > 0 &&
    Math.abs(frames[low - 1].timestamp_seconds - time) <=
      Math.abs(frames[low].timestamp_seconds - time)
  ) {
    return low - 1;
  }
  return low;
}

function Rig({
  frames,
  videoRef,
}: {
  frames: Pose3DFrame[];
  videoRef: React.RefObject<HTMLVideoElement | null>;
}) {
  const capsuleRefs = useRef<(THREE.Mesh | null)[]>([]);
  const capsuleMaterialRefs = useRef<(THREE.MeshStandardMaterial | null)[]>([]);
  const headRef = useRef<THREE.Mesh | null>(null);
  const headMaterialRef = useRef<THREE.MeshStandardMaterial | null>(null);
  const lastKnownLandmarksRef = useRef<Pose3DLandmarks | null>(null);
  const lastKnownColorRef = useRef<string>(DEFAULT_COLOR);

  useFrame(() => {
    const video = videoRef.current;
    if (!video || frames.length === 0) return;

    const index = findNearestFrameIndex(frames, video.currentTime);
    const frame = frames[index];
    if (frame.landmarks) {
      lastKnownLandmarksRef.current = frame.landmarks;
      lastKnownColorRef.current = frame.action_level
        ? ACTION_LEVEL_COLORS[frame.action_level] ?? DEFAULT_COLOR
        : DEFAULT_COLOR;
    }
    const landmarks = lastKnownLandmarksRef.current;
    if (!landmarks) return;
    const color = lastKnownColorRef.current;

    SKELETON_CONNECTIONS.forEach(([startName, endName], i) => {
      const mesh = capsuleRefs.current[i];
      const material = capsuleMaterialRefs.current[i];
      const startCoords = landmarks[startName];
      const endCoords = landmarks[endName];
      if (!mesh || !material || !startCoords || !endCoords) return;

      const start = toThreeVector(startCoords);
      const end = toThreeVector(endCoords);
      const direction = new THREE.Vector3().subVectors(end, start);
      const boneLength = direction.length();
      const midpoint = new THREE.Vector3().addVectors(start, end).multiplyScalar(0.5);

      mesh.position.copy(midpoint);
      if (boneLength > 1e-4) {
        mesh.quaternion.setFromUnitVectors(
          new THREE.Vector3(0, 1, 0),
          direction.clone().normalize()
        );
        mesh.scale.set(1, boneLength, 1);
      }
      material.color.set(color);
    });

    const headCoords = landmarks[HEAD_LANDMARK];
    if (headRef.current && headMaterialRef.current && headCoords) {
      headRef.current.position.copy(toThreeVector(headCoords));
      headMaterialRef.current.color.set(color);
    }
  });

  return (
    <>
      {SKELETON_CONNECTIONS.map(([startName, endName], i) => (
        <Capsule
          key={`${startName}-${endName}`}
          ref={(mesh) => {
            capsuleRefs.current[i] = mesh;
          }}
          args={[CAPSULE_RADIUS, 1, 4, 8]}
        >
          <meshStandardMaterial
            ref={(material) => {
              capsuleMaterialRefs.current[i] = material;
            }}
            color={DEFAULT_COLOR}
          />
        </Capsule>
      ))}
      <Sphere ref={headRef} args={[HEAD_RADIUS, 16, 16]}>
        <meshStandardMaterial ref={headMaterialRef} color={DEFAULT_COLOR} />
      </Sphere>
    </>
  );
}

export function PostureAvatar3D({
  pose3dUrl,
  videoRef,
}: {
  pose3dUrl: string;
  videoRef: React.RefObject<HTMLVideoElement | null>;
}) {
  const [frames, setFrames] = useState<Pose3DFrame[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setFrames(null);
    setError(null);
    fetch(`${API_URL}${pose3dUrl}`)
      .then((response) => {
        if (!response.ok) throw new Error(`Erreur ${response.status}`);
        return response.json() as Promise<Pose3DFrame[]>;
      })
      .then((data) => {
        if (!cancelled) setFrames(data);
      })
      .catch(() => {
        if (!cancelled) setError("Impossible de charger les données de posture 3D.");
      });
    return () => {
      cancelled = true;
    };
  }, [pose3dUrl]);

  if (error) {
    return <p className="text-sm text-red-600">{error}</p>;
  }
  if (!frames) {
    return <p className="text-sm text-gray-500">Chargement de l&apos;avatar 3D...</p>;
  }
  if (!frames.some((frame) => frame.detected)) {
    return <p className="text-sm text-gray-500">Aucune posture détectée sur cette vidéo.</p>;
  }

  return (
    <div className="aspect-video w-full overflow-hidden rounded-lg bg-gray-900">
      <Canvas camera={{ position: [0, 0, 2.5], fov: 50 }}>
        <ambientLight intensity={0.6} />
        <directionalLight position={[2, 2, 2]} intensity={0.8} />
        <Rig frames={frames} videoRef={videoRef} />
        <OrbitControls target={[0, 0, 0]} />
      </Canvas>
    </div>
  );
}
```

- [ ] **Step 2: Vérifier que le projet compile**

Run: `cd web && npx tsc --noEmit`
Expected: aucune erreur de type (le composant n'est pas encore utilisé ailleurs, donc `tsc` doit passer sur ce seul fichier sans erreur d'import cassé).

- [ ] **Step 3: Commit**

```bash
git add web/app/PostureAvatar3D.tsx
git commit -m "feat: composant PostureAvatar3D (mannequin 3D piloté par la pose)"
```

---

## Task 7: `page.tsx` — intégrer l'avatar 3D à côté de la vidéo résultat

**Files:**
- Modify: `web/app/page.tsx`

**Interfaces:**
- Consumes: `PostureAvatar3D` (Task 6), `result.pose3d_url` (Task 4).
- Produces: rien de consommé par une tâche suivante — c'est la dernière tâche de code de cette tranche.

- [ ] **Step 1: Ajouter l'import et le champ manquant du type de réponse**

Dans `web/app/page.tsx`, ajouter l'import en haut du fichier (après les imports React existants) :

```tsx
import { PostureAvatar3D } from "./PostureAvatar3D";
```

Modifier le type `AnalysisResponse` :

```tsx
type AnalysisResponse = {
  summary: AnalysisSummary;
  annotated_video_url: string;
  csv_url: string;
  pose3d_url: string;
};
```

- [ ] **Step 2: Ajouter une ref sur la vidéo résultat**

Avec les autres `useRef` en haut du composant (après `fileInputRef`), ajouter :

```tsx
  const resultVideoRef = useRef<HTMLVideoElement | null>(null);
```

- [ ] **Step 3: Afficher l'avatar à côté de la vidéo dans la section résultat**

Remplacer :

```tsx
      {result && (
        <section className="flex flex-col gap-4 rounded border p-4">
          <h2 className="text-lg font-semibold">Résultat</h2>
          <video
            src={`${API_URL}${result.annotated_video_url}`}
            controls
            className="w-full rounded-lg bg-black"
          />
```

par :

```tsx
      {result && (
        <section className="flex flex-col gap-4 rounded border p-4">
          <h2 className="text-lg font-semibold">Résultat</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <video
              ref={resultVideoRef}
              src={`${API_URL}${result.annotated_video_url}`}
              controls
              className="w-full rounded-lg bg-black"
            />
            <PostureAvatar3D pose3dUrl={result.pose3d_url} videoRef={resultVideoRef} />
          </div>
```

(Le `</div>` de fermeture s'ajoute juste avant le `<dl>` existant, qui reste inchangé en dehors de cette grille.)

- [ ] **Step 4: Vérifier que le projet compile**

Run: `cd web && npx tsc --noEmit`
Expected: aucune erreur de type

- [ ] **Step 5: Commit**

```bash
git add web/app/page.tsx
git commit -m "feat: affiche l'avatar 3D de posture à côté de la vidéo annotée"
```

---

## Task 8: Vérification manuelle de bout en bout sur une vraie vidéo

**Files:** aucun (vérification manuelle, pas de code).

**Interfaces:**
- Consumes: l'application complète (Tasks 1-7).
- Produces: rien — dernière étape de la tranche.

- [ ] **Step 1: Lancer les deux serveurs**

Terminal 1 :
```bash
PYTHONPATH=src venv/bin/uvicorn tms_vision.api:app --reload --port 8000
```

Terminal 2 :
```bash
cd web && npm run dev
```

- [ ] **Step 2: Analyser une vraie vidéo**

Ouvrir `http://localhost:3000`, cliquer « Importer une vidéo », choisir `~/Downloads/moi coupe.mp4` (ou une vidéo équivalente filmant une personne de profil), remplir le formulaire, cliquer « Analyser ».

- [ ] **Step 3: Vérifier visuellement l'avatar 3D**

Une fois le résultat affiché :
- Vérifier que l'avatar 3D (capsules + tête) apparaît à côté de la vidéo, dans une orientation cohérente (pas à l'envers, pas en miroir). Si l'avatar est à l'envers ou en miroir, ajuster le signe des axes dans `toThreeVector()` (`web/app/PostureAvatar3D.tsx`) en conséquence, puis recommencer cette étape.
- Lancer la lecture de la vidéo et vérifier que l'avatar suit la posture en synchro (bras qui se lève dans la vidéo = bras qui se lève sur l'avatar).
- Déplacer le curseur de lecture de la vidéo et vérifier que l'avatar se met à jour en conséquence (pas seulement pendant la lecture continue).
- Faire glisser la souris sur la scène 3D et vérifier que la caméra tourne/zoome (OrbitControls).
- Vérifier que la couleur de l'avatar change de façon cohérente avec le score RULA affiché (vert = acceptable, jusqu'à rouge = changement immédiat).

- [ ] **Step 4: Vérifier le cas "aucune pose détectée"**

Importer un clip sans personne dedans (ex. `samples/synthetic_smoke_test.mp4`) et vérifier que le message « Aucune posture détectée sur cette vidéo. » s'affiche à la place de la scène 3D, sans erreur dans la console navigateur.

- [ ] **Step 5: Documenter le résultat dans le README**

Une fois la vérification validée, mettre à jour la section 8 du `README.md` (Feuille de Route de Déploiement) pour marquer cette tranche comme livrée, dans le même style que les tranches précédentes (✅ Tranche ... — TERMINÉE, avec un court résumé de ce qui a été vérifié).

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: valide la tranche 1 de l'avatar 3D de posture sur une vraie vidéo"
```
