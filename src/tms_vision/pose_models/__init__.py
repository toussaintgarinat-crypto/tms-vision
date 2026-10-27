"""Modèles de pose interchangeables, au format de sortie normalisé (voir schema.py)."""
from tms_vision.pose_models.base import (
    BasePoseModel, ModelMetadata, ModelUnavailableError, PoseModelError, VideoUnreadableError,
)
from tms_vision.pose_models.registry import DEFAULT_MODEL, available_models, create_model, register
from tms_vision.pose_models.schema import (
    FramePose, Keypoint, group_of, keypoints_to_landmarks, landmarks_to_keypoints,
)

__all__ = [
    "BasePoseModel", "ModelMetadata", "ModelUnavailableError", "PoseModelError",
    "VideoUnreadableError", "DEFAULT_MODEL", "available_models", "create_model", "register",
    "FramePose", "Keypoint", "group_of", "keypoints_to_landmarks", "landmarks_to_keypoints",
]
