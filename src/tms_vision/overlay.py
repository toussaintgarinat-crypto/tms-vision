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
