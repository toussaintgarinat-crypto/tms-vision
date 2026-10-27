"""Points personnalisés (outil, caisse, pièce, zone de danger...) : l'utilisateur les place à la
main sur une image de référence ; ils sont ensuite suivis image par image par flux optique
Lucas-Kanade (OpenCV, sans dépendance supplémentaire).

Un point suivi est vérifié par un suivi retour (aller-retour) : si le point retrouvé ne revient pas
près de son point de départ, il est considéré perdu pour cette image (omis, pas d'erreur). Un point
perdu plus de MAX_LOST_FRAMES images de suite est abandonné. Le suivi est dans le sens de la
vidéo à partir de l'image de référence : avant elle, aucun point.

Un modèle de détection entraîné (YOLO...) pourra remplacer ce suivi plus tard derrière la même
interface, sans changer le format de sortie.
"""
import re
import unicodedata
from dataclasses import dataclass

import cv2
import numpy as np

from tms_vision.pose_models.base import BasePoseModel, ModelMetadata, PoseModelError
from tms_vision.pose_models.schema import FramePose, Keypoint

MODEL_ID = "custom_keypoints"
MAX_POINTS = 10
MAX_LOST_FRAMES = 15
# Erreur aller-retour (en pixels) au-delà de laquelle un point est rejeté ; en dessous, la confiance
# décroît linéairement de 1 (erreur nulle) à 0 (erreur = FB_MAX_ERROR).
FB_MAX_ERROR = 2.0
_LK_PARAMS = dict(winSize=(21, 21), maxLevel=3,
                  criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))


def slugify(label: str) -> str:
    """`Clé à molette` -> `cle_a_molette` : nom de point utilisable (`custom_<slug>`)."""
    text = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:30]


@dataclass(frozen=True)
class CustomPoint:
    name: str  # slug, sans le préfixe `custom_`
    x: float  # normalisé [0, 1] sur l'image de référence
    y: float
    label: str = ""

    @property
    def keypoint_name(self) -> str:
        return f"custom_{self.name}"


@dataclass(frozen=True)
class CustomSpec:
    points: tuple[CustomPoint, ...]
    reference_time_seconds: float = 0.0

    @classmethod
    def from_dict(cls, data: dict) -> "CustomSpec":
        """Valide et normalise la saisie de l'interface. Lève `PoseModelError` si elle est invalide."""
        if not isinstance(data, dict) or not isinstance(data.get("points"), list):
            raise PoseModelError("Points personnalisés : un objet avec une liste « points » est attendu.")
        raw_points = data["points"]
        if not 1 <= len(raw_points) <= MAX_POINTS:
            raise PoseModelError(f"Points personnalisés : entre 1 et {MAX_POINTS} points attendus.")
        points, seen = [], set()
        for index, raw in enumerate(raw_points, start=1):
            try:
                x, y = float(raw["x"]), float(raw["y"])
            except (KeyError, TypeError, ValueError):
                raise PoseModelError(f"Point personnalisé {index} : coordonnées x et y manquantes.") from None
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise PoseModelError(f"Point personnalisé {index} : x et y doivent être entre 0 et 1.")
            label = str(raw.get("name") or f"point {index}").strip()[:60]
            slug = slugify(label) or f"point_{index}"
            if slug in seen:
                raise PoseModelError(f"Point personnalisé « {label} » : nom en double.")
            seen.add(slug)
            points.append(CustomPoint(name=slug, x=x, y=y, label=label))
        try:
            reference = float(data.get("reference_time_seconds", 0.0))
        except (TypeError, ValueError):
            raise PoseModelError("Points personnalisés : reference_time_seconds invalide.") from None
        if not np.isfinite(reference) or reference < 0:
            raise PoseModelError("Points personnalisés : reference_time_seconds doit être positif.")
        return cls(points=tuple(points), reference_time_seconds=reference)

    def to_dict(self) -> dict:
        return {
            "reference_time_seconds": self.reference_time_seconds,
            "points": [{"name": p.label or p.name, "x": p.x, "y": p.y} for p in self.points],
        }


class CustomKeypointsModel(BasePoseModel):
    metadata = ModelMetadata(
        id=MODEL_ID, label="Custom keypoints", keypoint_count=0, groups=("custom",),
        description="Points d'intérêt placés à la main sur une image, suivis dans la vidéo.",
        primary=False,
    )

    def __init__(self, spec: CustomSpec) -> None:
        super().__init__()
        self._spec = spec
        self._positions: dict[str, np.ndarray] = {}  # dernière position connue (pixels)
        self._lost: dict[str, int] = {}  # images perdues de suite ; absent = suivi sain
        self._previous_gray: np.ndarray | None = None
        self._started = False

    def load(self) -> None:
        """Rien à charger (OpenCV est déjà là)."""

    def process_frame(
        self, frame: np.ndarray, frame_index: int = 0, timestamp_seconds: float | None = None,
    ) -> list[FramePose]:
        """`timestamp_seconds` : instant de l'image, comparé à `reference_time_seconds` ; sans lui,
        l'image de référence est la première image reçue."""
        height, width = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if not self._started:
            if timestamp_seconds is not None and timestamp_seconds + 1e-6 < self._spec.reference_time_seconds:
                self._last = []
                return self._last
            self._started = True
            self._positions = {
                p.keypoint_name: np.array([p.x * width, p.y * height], dtype=np.float32)
                for p in self._spec.points
            }
            self._previous_gray = gray
            return self._emit(frame_index, width, height, {n: 1.0 for n in self._positions})

        confidences = self._track(gray, width, height)
        self._previous_gray = gray
        return self._emit(frame_index, width, height, confidences)

    def _track(self, gray: np.ndarray, width: int, height: int) -> dict[str, float]:
        """Confiance (0-1) des points suivis cette image ; un point perdu est absent du résultat."""
        names = [n for n in self._positions if self._lost.get(n, 0) <= MAX_LOST_FRAMES]
        if not names or self._previous_gray is None:
            return {}
        start = np.array([self._positions[n] for n in names], dtype=np.float32).reshape(-1, 1, 2)
        moved, status, _ = cv2.calcOpticalFlowPyrLK(self._previous_gray, gray, start, None, **_LK_PARAMS)
        back, back_status, _ = cv2.calcOpticalFlowPyrLK(gray, self._previous_gray, moved, None, **_LK_PARAMS)
        confidences: dict[str, float] = {}
        for i, name in enumerate(names):
            x, y = moved[i, 0]
            fb_error = float(np.linalg.norm(back[i, 0] - start[i, 0]))
            inside = 0 <= x < width and 0 <= y < height
            if status[i, 0] == 1 and back_status[i, 0] == 1 and inside and fb_error <= FB_MAX_ERROR:
                self._positions[name] = moved[i, 0]
                self._lost.pop(name, None)
                confidences[name] = round(max(0.0, 1.0 - fb_error / FB_MAX_ERROR), 3)
            else:
                self._lost[name] = self._lost.get(name, 0) + 1
        return confidences

    def _emit(self, frame_index: int, width: int, height: int, confidences: dict[str, float]) -> list[FramePose]:
        keypoints = [
            Keypoint(name=name, x=float(self._positions[name][0]) / width,
                     y=float(self._positions[name][1]) / height, confidence=conf, visibility=conf)
            for name, conf in confidences.items()
        ]
        self._last = [FramePose(frame=frame_index, model=MODEL_ID, keypoints=keypoints)] if keypoints else []
        return self._last
