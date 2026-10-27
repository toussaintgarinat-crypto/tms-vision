"""Point de pose 2D/3D, sans dépendance à un modèle (importable sans MediaPipe)."""
from dataclasses import dataclass


@dataclass
class Landmark:
    x: float
    y: float
    z: float
    visibility: float
