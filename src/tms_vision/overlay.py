"""Rendu du squelette et du badge de score RULA sur une frame vidéo."""
import cv2
import numpy as np

from tms_vision.pose_estimation import Landmark
from tms_vision.pose_models.mediapipe_hands import HAND_CONNECTIONS, hand_point_names
from tms_vision.pose_models.schema import Keypoint
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


# Couleur des points par groupe (BGR). Le corps garde le blanc historique.
GROUP_COLORS = {
    "body": (255, 255, 255),
    "hands": (0, 165, 255),  # orange
    "feet": (255, 200, 0),  # bleu clair
    "face": (200, 120, 255),  # rose
    "custom": (0, 230, 230),  # jaune
}


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


def _draw_extra_keypoints(image: np.ndarray, keypoints: list[Keypoint]) -> None:
    """Points hors corps, colorés par groupe : mains (avec doigts reliés), pieds, visage, custom."""
    height, width = image.shape[:2]
    by_name = {k.name: k for k in keypoints}
    for side in ("left", "right"):
        points = [by_name.get(name) for name in hand_point_names(side)]
        for a, b in HAND_CONNECTIONS:
            if points[a] is not None and points[b] is not None:
                cv2.line(image, (int(points[a].x * width), int(points[a].y * height)),
                         (int(points[b].x * width), int(points[b].y * height)),
                         GROUP_COLORS["hands"], 1)
    for keypoint in keypoints:
        group = keypoint.group
        if group == "body":
            continue
        radius = 3 if group in ("feet", "custom") else 2
        center = (int(keypoint.x * width), int(keypoint.y * height))
        cv2.circle(image, center, radius, GROUP_COLORS[group], -1)
        if group == "custom":
            cv2.circle(image, center, radius + 4, GROUP_COLORS[group], 1)
            cv2.putText(image, keypoint.name[len("custom_"):], (center[0] + 9, center[1] - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, GROUP_COLORS[group], 1, cv2.LINE_AA)


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
    image_bgr: np.ndarray, landmarks: dict[str, Landmark] | None, score: RulaScore | None,
    extra_keypoints: list[Keypoint] | None = None,
) -> np.ndarray:
    output = image_bgr.copy()
    if landmarks is not None:
        _draw_skeleton(output, landmarks)
    if extra_keypoints:
        _draw_extra_keypoints(output, extra_keypoints)
    if score is not None:
        _draw_score_badge(output, score)
    return output
