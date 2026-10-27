"""MediaPipe Pose, 33 points : modèle historique et par défaut. Enveloppe `PoseEstimator`
sans en changer le comportement."""
import numpy as np

from tms_vision.pose_models.base import BasePoseModel, ModelMetadata, ModelUnavailableError
from tms_vision.pose_models.schema import FramePose, landmarks_to_keypoints

MODEL_ID = "mediapipe_pose_33"


class MediaPipePoseModel(BasePoseModel):
    metadata = ModelMetadata(
        id=MODEL_ID, label="MediaPipe Pose 33", keypoint_count=33,
        groups=("body", "face", "feet", "hands"),
        description="Modèle actuel, rapide et léger. Score RULA et analyse ergonomique globale.",
        requires=("mediapipe",),
    )

    def __init__(self, min_visibility: float = 0.5) -> None:
        super().__init__()
        self._min_visibility = min_visibility
        self._estimator = None

    def load(self) -> None:
        if self._estimator is not None:
            return
        try:
            from tms_vision.pose_estimation import PoseEstimator
        except ImportError as error:
            raise ModelUnavailableError(
                "MediaPipe n'est pas installé (pip install 'mediapipe>=0.10.14,<0.10.30', "
                "Python 3.11)."
            ) from error
        self._estimator = PoseEstimator(min_visibility=self._min_visibility)

    def process_frame(self, frame: np.ndarray, frame_index: int = 0) -> list[FramePose]:
        self.load()
        result = self._estimator.process(frame)
        keypoints = landmarks_to_keypoints(result.landmarks)
        self._last = [FramePose(frame=frame_index, model=MODEL_ID, keypoints=keypoints)] if keypoints else []
        return self._last

    def close(self) -> None:
        if self._estimator is not None:
            self._estimator.close()
            self._estimator = None
