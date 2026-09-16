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
