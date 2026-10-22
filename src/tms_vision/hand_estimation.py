"""Wrapper autour de MediaPipe Hands : flexion des doigts de la main du côté analysé."""
import cv2
import mediapipe as mp
import numpy as np

from tms_vision.extremities import finger_curl_deg
from tms_vision.pose_estimation import Landmark

# Distance maximale (fraction de la diagonale de l'image) entre le poignet de Pose et celui de
# Hands pour considérer qu'il s'agit de la même main.
MAX_WRIST_DISTANCE = 0.15


class HandEstimator:
    def __init__(self) -> None:
        self._hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def finger_curl(self, image_bgr: np.ndarray, pose_wrist: Landmark | None) -> float | None:
        """Flexion moyenne des doigts de la main dont le poignet est le plus proche du poignet
        donné par Pose, ou `None` (pas de main, ou main trop éloignée : autre personne, autre bras)."""
        if pose_wrist is None:
            return None
        results = self._hands.process(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
        if not results.multi_hand_landmarks:
            return None
        height, width = image_bgr.shape[:2]
        best = None
        best_distance = MAX_WRIST_DISTANCE
        for hand in results.multi_hand_landmarks:
            wrist = hand.landmark[0]
            distance = float(np.hypot((wrist.x - pose_wrist.x) * width / np.hypot(width, height),
                                      (wrist.y - pose_wrist.y) * height / np.hypot(width, height)))
            if distance < best_distance:
                best, best_distance = hand, distance
        if best is None:
            return None
        return finger_curl_deg([(p.x, p.y) for p in best.landmark], aspect=width / height)

    def close(self) -> None:
        self._hands.close()
