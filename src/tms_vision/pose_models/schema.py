"""Format normalisé de sortie commun à tous les modèles de pose.

Les calculs en aval (angles, RULA, export, overlay) consomment ce format et jamais la sortie brute
d'un modèle. Les noms de points sont en minuscules (`left_wrist`, `right_index_tip`...). Coordonnées
x, y normalisées dans [0, 1] (image), z relatif (même échelle que x), comme MediaPipe.
"""
from dataclasses import dataclass, field

from tms_vision.landmark import Landmark

# Groupes de points, utilisés pour colorer l'overlay et filtrer l'affichage.
GROUPS = ("body", "hands", "feet", "face", "custom")

_FACE_NAMES = {
    "nose", "left_eye_inner", "left_eye", "left_eye_outer", "right_eye_inner", "right_eye",
    "right_eye_outer", "left_ear", "right_ear", "mouth_left", "mouth_right",
}
_FOOT_NAMES = {"left_ankle", "right_ankle", "left_heel", "right_heel",
               "left_foot_index", "right_foot_index"}
_HAND_NAMES = {f"{side}_{finger}" for side in ("left", "right")
               for finger in ("pinky", "index", "thumb")}  # points « main » de MediaPipe Pose


def group_of(name: str) -> str:
    """Groupe d'un point d'après son nom standardisé."""
    if name.startswith("custom_"):
        return "custom"
    if name in _FACE_NAMES or name.startswith("face_"):
        return "face"
    if name in _FOOT_NAMES or "toe" in name or "foot" in name:
        return "feet"
    if name in _HAND_NAMES or name.startswith(("left_hand_", "right_hand_")) \
            or name.endswith(("_tip", "_dip", "_pip", "_mcp", "_cmc")):
        return "hands"
    return "body"


@dataclass
class Keypoint:
    name: str
    x: float
    y: float
    z: float = 0.0
    confidence: float = 1.0
    visibility: float = 1.0

    @property
    def group(self) -> str:
        return group_of(self.name)

    def to_dict(self) -> dict:
        return {"name": self.name, "x": self.x, "y": self.y, "z": self.z,
                "confidence": self.confidence, "visibility": self.visibility}


@dataclass
class FramePose:
    """Les points d'une personne sur une image."""
    frame: int
    model: str
    keypoints: list[Keypoint] = field(default_factory=list)
    person_id: int = 1

    def by_name(self) -> dict[str, Keypoint]:
        return {k.name: k for k in self.keypoints}

    def to_dict(self) -> dict:
        return {"frame": self.frame, "person_id": self.person_id, "model": self.model,
                "keypoints": [k.to_dict() for k in self.keypoints]}

    @classmethod
    def from_dict(cls, data: dict) -> "FramePose":
        return cls(
            frame=data["frame"], model=data["model"], person_id=data.get("person_id", 1),
            keypoints=[Keypoint(**k) for k in data.get("keypoints", [])],
        )


def landmarks_to_keypoints(landmarks: dict[str, Landmark] | None) -> list[Keypoint]:
    """Landmarks MediaPipe (clés `LEFT_WRIST`) -> points normalisés (`left_wrist`)."""
    if not landmarks:
        return []
    return [
        Keypoint(name=name.lower(), x=lm.x, y=lm.y, z=lm.z,
                 confidence=lm.visibility, visibility=lm.visibility)
        for name, lm in landmarks.items()
    ]


def keypoints_to_landmarks(keypoints: list[Keypoint]) -> dict[str, Landmark]:
    """Passerelle inverse : permet à angles.py / RULA (qui lisent des `Landmark` aux clés
    majuscules) de consommer le format normalisé tel quel, sans connaître le modèle. Un modèle qui
    ne fournit pas un point donne simplement un dictionnaire sans cette clé."""
    return {
        k.name.upper(): Landmark(x=k.x, y=k.y, z=k.z, visibility=k.visibility)
        for k in keypoints
    }
