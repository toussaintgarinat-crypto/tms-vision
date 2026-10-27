"""Indicateurs de la main à partir des 21 points de MediaPipe Hands (format normalisé).

Flexion des doigts par image, puis par vidéo : nombre et durée des préhensions, cadence (gestes
répétitifs). Hors RULA, comme le reste des extrémités (voir extremities.py). Seuils lus dans
extremity_thresholds.json (`hand`), non calibrés. Module pur."""
from tms_vision.extremities import finger_curl_deg
from tms_vision.pose_models.mediapipe_hands import hand_point_names
from tms_vision.pose_models.schema import Keypoint

# Une main non vue pendant plus longtemps que cela met fin à la préhension en cours.
MAX_GAP_SECONDS = 0.5
# En dessous de cette durée de vidéo, une cadence (préhensions par minute) n'aurait aucun sens.
MIN_SECONDS_FOR_RATE = 5.0


def finger_curl_from_keypoints(keypoints: list[Keypoint], side: str, aspect: float = 1.0) -> float | None:
    """Flexion moyenne des doigts longs de la main `side`, ou `None` si ses 21 points manquent."""
    by_name = {k.name: k for k in keypoints}
    names = hand_point_names(side)
    if any(name not in by_name for name in names):
        return None
    return finger_curl_deg([(by_name[n].x, by_name[n].y) for n in names], aspect=aspect)


class GripAccumulator:
    """Suit une main image par image. Une préhension commence quand la flexion des doigts atteint
    `on_deg` et se termine quand elle retombe sous `on_deg - hysteresis_deg` (l'écart évite de
    compter plusieurs préhensions pour une flexion qui oscille autour du seuil)."""

    def __init__(self, thresholds: dict) -> None:
        hand = thresholds["hand"]
        self._on = float(hand["finger_curl_bounds_deg"][0])
        self._off = self._on - float(hand.get("grasp_hysteresis_deg", 10.0))
        self._repetitive_per_minute = float(hand.get("repetitive_grasps_per_minute", 30.0))
        self._grasping = False
        self._last_seen: float | None = None
        self._first_ts: float | None = None
        self._last_ts: float = 0.0
        self.frames = 0
        self.detected = 0
        self.grasp_count = 0
        self.grasp_seconds = 0.0
        self._curls: list[float] = []

    def update(self, timestamp: float, curl: float | None) -> None:
        if self._first_ts is None:
            self._first_ts = timestamp
        self.frames += 1
        self._last_ts = timestamp
        if curl is None:
            if self._grasping and self._last_seen is not None and timestamp - self._last_seen > MAX_GAP_SECONDS:
                self._grasping = False
            return
        self.detected += 1
        self._curls.append(curl)
        if self._grasping and self._last_seen is not None:
            self.grasp_seconds += max(timestamp - self._last_seen, 0.0)
        self._last_seen = timestamp
        if not self._grasping and curl >= self._on:
            self._grasping = True
            self.grasp_count += 1
        elif self._grasping and curl < self._off:
            self._grasping = False

    def summary(self) -> dict:
        duration = max(self._last_ts - (self._first_ts or 0.0), 0.0)
        per_minute = self.grasp_count / (duration / 60.0) if duration >= MIN_SECONDS_FOR_RATE else None
        return {
            "detected_frame_count": self.detected,
            "detection_ratio": round(self.detected / self.frames, 3) if self.frames else 0.0,
            "finger_curl_mean_deg": round(sum(self._curls) / len(self._curls), 1) if self._curls else None,
            "finger_curl_max_deg": round(max(self._curls), 1) if self._curls else None,
            "grasp_count": self.grasp_count,
            "grasp_seconds": round(self.grasp_seconds, 2),
            "grasps_per_minute": round(per_minute, 1) if per_minute is not None else None,
            "repetitive": bool(per_minute is not None and per_minute >= self._repetitive_per_minute),
        }
