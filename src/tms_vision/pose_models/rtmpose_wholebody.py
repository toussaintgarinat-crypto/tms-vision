"""RTMPose whole-body (COCO-WholeBody, 133 points : corps, pieds, visage, mains) via `rtmlib`.

RTMW-x (famille RTMPose/DWPose distillée, la variante la plus précise de rtmlib), open source
(Apache 2.0), exécuté par ONNX Runtime, sans PyTorch. Installation facultative :
`pip install -r requirements-wholebody.txt`. Les poids sont téléchargés au premier usage dans le
cache de rtmlib. Le mode `performance` (le plus précis, RTMPose-x) est celui par défaut ; le mode
se règle avec la variable d'environnement TMS_WHOLEBODY_MODE (performance, balanced, lightweight).

Le modèle est 2D : pas de points « monde », donc ni avatar 3D ni angle de cheville.
"""
import os

import numpy as np

from tms_vision.landmark import Landmark
from tms_vision.pose_models.base import BasePoseModel, ModelMetadata, ModelUnavailableError
from tms_vision.pose_models.mediapipe_hands import hand_point_names
from tms_vision.pose_models.schema import FramePose, Keypoint

MODEL_ID = "rtmpose_wholebody_133"

_BODY = (
    "nose", "left_eye", "right_eye", "left_ear", "right_ear", "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow", "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
)
_FEET = ("left_big_toe", "left_small_toe", "left_heel", "right_big_toe", "right_small_toe", "right_heel")
_FACE = tuple(f"face_{i}" for i in range(68))
# Ordre COCO-WholeBody : corps 0-16, pieds 17-22, visage 23-90, main gauche 91-111, main droite 112-132.
# L'ordre des 21 points d'une main est celui de MediaPipe Hands (poignet, pouce, index, ...).
KEYPOINT_NAMES = _BODY + _FEET + _FACE + tuple(hand_point_names("left")) + tuple(hand_point_names("right"))
assert len(KEYPOINT_NAMES) == 133

# Groupes demandés par les options (le corps est toujours gardé).
_GROUP_SLICES = {"body": (0, 17), "feet": (17, 23), "face": (23, 91), "hands": (91, 133)}

# Les scores bruts de RTMW ne sont pas des probabilités : mesurés sur une image vide, un portrait
# (jambes hors champ) et une vidéo de poste, un point non visible donne environ 0,6 à 2,1 et un
# point visible 3,3 à 8. On les ramène à une confiance 0-1 (0 en dessous de SCORE_FLOOR, 1 au-dessus
# de SCORE_FULL). Valeurs empiriques, à réviser si le modèle change (mode TMS_WHOLEBODY_MODE).
SCORE_FLOOR = 1.5
SCORE_FULL = 5.0

# Seuils de confiance (après conversion) : les points qui alimentent les angles sont plus exigeants
# que les points supplémentaires conservés pour l'affichage et l'export.
BODY_MIN_SCORE = 0.3
EXTRA_MIN_SCORE = 0.25


def score_to_confidence(score: float) -> float:
    return float(np.clip((score - SCORE_FLOOR) / (SCORE_FULL - SCORE_FLOOR), 0.0, 1.0))


def keypoint_count(hands: bool, feet: bool, face: bool) -> int:
    return 17 + (42 if hands else 0) + (6 if feet else 0) + (68 if face else 0)


def to_pose_landmarks(pose: FramePose) -> dict[str, Landmark]:
    """Passerelle vers les `Landmark` aux noms MediaPipe que lisent angles.py et RULA.

    - Les 17 points du corps portent les mêmes noms (`LEFT_SHOULDER`...).
    - `*_INDEX` (base de l'index, repère du poignet RULA) = `*_index_mcp` de la main ;
    - `*_HEEL` et `*_FOOT_INDEX` (bout du pied) = talon et gros orteil.
    Un point absent ou peu fiable est simplement omis : les calculs qui en dépendent sont ignorés."""
    landmarks: dict[str, Landmark] = {}
    aliases = {}
    for side in ("left", "right"):
        aliases[f"{side}_index_mcp"] = f"{side}_index"
        aliases[f"{side}_big_toe"] = f"{side}_foot_index"
    for k in pose.keypoints:
        if k.confidence < BODY_MIN_SCORE:
            continue
        name = aliases.get(k.name, k.name if k.name in _BODY or k.name.endswith("_heel") else None)
        if name is not None:
            landmarks[name.upper()] = Landmark(x=k.x, y=k.y, z=0.0, visibility=k.visibility)
    return landmarks


def _person_keypoints(points: np.ndarray, scores: np.ndarray, width: int, height: int,
                      groups: set[str], frame_index: int) -> FramePose:
    keypoints = []
    for group, (start, stop) in _GROUP_SLICES.items():
        if group != "body" and group not in groups:
            continue
        for index in range(start, stop):
            score = score_to_confidence(float(scores[index]))
            if score < EXTRA_MIN_SCORE:
                continue
            x, y = points[index]
            keypoints.append(Keypoint(
                name=KEYPOINT_NAMES[index], x=float(x) / width, y=float(y) / height,
                z=0.0, confidence=score, visibility=score,
            ))
    return FramePose(frame=frame_index, model=MODEL_ID, keypoints=keypoints)


def choose_person(points: np.ndarray, scores: np.ndarray) -> int | None:
    """Indice de la personne retenue (l'analyse suit une seule personne) : la plus grande dans
    l'image parmi celles dont le corps est assez fiable."""
    best, best_area = None, 0.0
    for i in range(len(points)):
        if np.mean([score_to_confidence(float(s)) for s in scores[i][:17]]) < EXTRA_MIN_SCORE:
            continue
        body = points[i][:17]
        area = float(np.ptp(body[:, 0]) * np.ptp(body[:, 1]))
        if area > best_area:
            best, best_area = i, area
    return best


class RTMPoseWholeBodyModel(BasePoseModel):
    metadata = ModelMetadata(
        id=MODEL_ID, label="RTMPose Whole-body 133", keypoint_count=133,
        groups=("body", "feet", "face", "hands"),
        description="Corps, pieds, visage et mains (RTMW-x, open source, ONNX). 2D : ni avatar 3D ni cheville.",
        requires=("rtmlib", "onnxruntime"),
    )

    def __init__(self, hands: bool = True, feet: bool = True, face: bool = False,
                 mode: str | None = None) -> None:
        super().__init__()
        self._groups = {g for g, on in (("hands", hands), ("feet", feet), ("face", face)) if on}
        self._mode = mode or os.environ.get("TMS_WHOLEBODY_MODE", "performance")
        self._model = None

    def load(self) -> None:
        if self._model is not None:
            return
        try:
            from rtmlib import Wholebody
        except ImportError as error:
            raise ModelUnavailableError(
                "Le modèle whole-body n'est pas installé : pip install -r requirements-wholebody.txt "
                "(rtmlib + onnxruntime)."
            ) from error
        try:
            self._model = Wholebody(mode=self._mode, backend="onnxruntime", device="cpu")
        except Exception as error:  # téléchargement des poids, fichier ONNX illisible...
            raise ModelUnavailableError(
                f"Impossible de charger le modèle whole-body (mode {self._mode!r}) : {error}"
            ) from error

    def process_frame(self, frame: np.ndarray, frame_index: int = 0) -> list[FramePose]:
        self.load()
        height, width = frame.shape[:2]
        points, scores = self._model(frame)
        points, scores = np.asarray(points), np.asarray(scores)
        if points.ndim != 3 or len(points) == 0:
            self._last = []
            return self._last
        person = choose_person(points, scores)
        if person is None:
            self._last = []
            return self._last
        self._last = [_person_keypoints(points[person], scores[person], width, height,
                                        self._groups, frame_index)]
        return self._last

    def close(self) -> None:
        self._model = None


class WholeBodyPoseEstimator:
    """Même interface que `PoseEstimator` (`process`, `close`), pour que le pipeline utilise
    RTMPose sans autre changement : renvoie un `PoseResult` (sans points monde) et garde les
    points complémentaires de la dernière image dans `last_pose`."""

    def __init__(self, hands: bool, feet: bool, face: bool) -> None:
        self._model = RTMPoseWholeBodyModel(hands=hands, feet=feet, face=face)
        self._model.load()
        self.last_pose: FramePose | None = None

    def process(self, image_bgr: np.ndarray):
        from tms_vision.pose_estimation import PoseResult

        poses = self._model.process_frame(image_bgr)
        self.last_pose = poses[0] if poses else None
        landmarks = to_pose_landmarks(self.last_pose) if self.last_pose else {}
        return PoseResult(landmarks=landmarks or None, world_landmarks=None)

    def close(self) -> None:
        self._model.close()
