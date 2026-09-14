import numpy as np
from tms_vision.pose_estimation import PoseEstimator


def test_blank_frame_returns_no_landmarks():
    estimator = PoseEstimator()
    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    result = estimator.process(blank)
    estimator.close()

    assert result.landmarks is None
