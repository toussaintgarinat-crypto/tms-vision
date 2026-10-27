"""Interface commune des modèles de pose."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator

import numpy as np

from tms_vision.capture import FrameSource
from tms_vision.pose_models.schema import FramePose


class PoseModelError(RuntimeError):
    """Erreur de base des modèles de pose."""


class ModelUnavailableError(PoseModelError):
    """Dépendance ou fichier de poids du modèle absent (message d'installation inclus)."""


class VideoUnreadableError(PoseModelError):
    """La vidéo ne peut pas être ouverte ou ne contient aucune image."""


@dataclass(frozen=True)
class ModelMetadata:
    id: str
    label: str
    keypoint_count: int
    groups: tuple[str, ...]
    description: str = ""
    requires: tuple[str, ...] = field(default_factory=tuple)  # paquets Python nécessaires
    primary: bool = True  # False : modèle complémentaire (mains), choisi par une option, pas seul


class BasePoseModel(ABC):
    """Un modèle = un adaptateur qui transforme une image en `FramePose` normalisés.

    `process_frame` renvoie une liste (une entrée par personne ; vide si personne/main détecté :
    ce n'est pas une erreur). Les erreurs d'installation sont levées par `load()`.
    """

    metadata: ModelMetadata

    def __init__(self) -> None:
        self._last: list[FramePose] = []

    @abstractmethod
    def load(self) -> None:
        """Charge le modèle. Lève `ModelUnavailableError` s'il n'est pas installé."""

    @abstractmethod
    def process_frame(self, frame: np.ndarray, frame_index: int = 0) -> list[FramePose]:
        """Traite une image BGR."""

    def close(self) -> None:
        """Libère les ressources (facultatif)."""

    def get_keypoints(self) -> list[FramePose]:
        """Résultat de la dernière image traitée."""
        return self._last

    def get_metadata(self) -> ModelMetadata:
        return self.metadata

    def iter_video(self, video_path: str) -> Iterator[list[FramePose]]:
        try:
            source = FrameSource(video_path)
        except FileNotFoundError as error:
            raise VideoUnreadableError(str(error)) from error
        except RuntimeError as error:
            raise VideoUnreadableError(str(error)) from error
        try:
            seen = False
            for frame in source:
                seen = True
                self._last = self.process_frame(frame.image, frame.index)
                yield self._last
            if not seen:
                raise VideoUnreadableError(f"Vidéo vide ou illisible : {video_path}")
        finally:
            source.release()

    def process_video(self, video_path: str) -> list[list[FramePose]]:
        """Toutes les images d'une vidéo (une liste de personnes par image)."""
        return list(self.iter_video(video_path))
