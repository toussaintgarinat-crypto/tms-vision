"""Registre des modèles de pose : l'API choisit un modèle par son identifiant."""
import importlib.util
from typing import Callable

from tms_vision.pose_models.base import BasePoseModel, ModelMetadata, PoseModelError
from tms_vision.pose_models.mediapipe_pose import MODEL_ID as MEDIAPIPE_POSE_33, MediaPipePoseModel

from tms_vision.pose_models.custom_keypoints import CustomKeypointsModel, MODEL_ID as CUSTOM_KEYPOINTS
from tms_vision.pose_models.mediapipe_hands import MODEL_ID as MEDIAPIPE_HANDS, MediaPipeHandsModel
from tms_vision.pose_models.rtmpose_wholebody import MODEL_ID as RTMPOSE_WHOLEBODY, RTMPoseWholeBodyModel

DEFAULT_MODEL = MEDIAPIPE_POSE_33

_FACTORIES: dict[str, Callable[..., BasePoseModel]] = {}


def register(model_id: str, factory: Callable[..., BasePoseModel]) -> None:
    _FACTORIES[model_id] = factory


def available_models() -> list[dict]:
    """Description de chaque modèle pour le sélecteur (avec indication d'installation)."""
    out = []
    for model_id, factory in _FACTORIES.items():
        meta: ModelMetadata = factory.metadata
        out.append({
            "id": model_id, "label": meta.label, "keypoint_count": meta.keypoint_count,
            "groups": list(meta.groups), "description": meta.description,
            "primary": meta.primary,
            "installed": all(importlib.util.find_spec(p) is not None for p in meta.requires),
            "default": model_id == DEFAULT_MODEL,
        })
    return out


def create_model(model_id: str | None = None, **options) -> BasePoseModel:
    """Instancie (sans charger) le modèle demandé ; `None` = modèle par défaut."""
    model_id = model_id or DEFAULT_MODEL
    try:
        factory = _FACTORIES[model_id]
    except KeyError:
        raise PoseModelError(
            f"Modèle de pose inconnu : {model_id!r} (disponibles : {', '.join(_FACTORIES)})"
        ) from None
    return factory(**options)


register(MEDIAPIPE_POSE_33, MediaPipePoseModel)
register(MEDIAPIPE_HANDS, MediaPipeHandsModel)
register(RTMPOSE_WHOLEBODY, RTMPoseWholeBodyModel)
register(CUSTOM_KEYPOINTS, CustomKeypointsModel)
