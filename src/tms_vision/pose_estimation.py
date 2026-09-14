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
