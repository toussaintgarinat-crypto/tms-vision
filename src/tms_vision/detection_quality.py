"""Qualité de détection d'une analyse : combien de points sont trouvés par image, avec quelle
confiance (affichée dans le dashboard à côté du modèle choisi). Module pur."""


class DetectionQualityAccumulator:
    def __init__(self) -> None:
        self._frames = 0
        self._frames_with_points = 0
        self._points = 0
        self._confidence_sum = 0.0

    def update(self, confidences: list[float]) -> None:
        """`confidences` : confiance (0-1) de chaque point trouvé sur l'image, tous modèles confondus."""
        self._frames += 1
        if not confidences:
            return
        self._frames_with_points += 1
        self._points += len(confidences)
        self._confidence_sum += sum(confidences)

    def summary(self) -> dict:
        return {
            "frames_with_points": self._frames_with_points,
            "avg_keypoints_per_frame": (
                round(self._points / self._frames_with_points, 1) if self._frames_with_points else 0.0
            ),
            "avg_confidence": round(self._confidence_sum / self._points, 3) if self._points else None,
        }
