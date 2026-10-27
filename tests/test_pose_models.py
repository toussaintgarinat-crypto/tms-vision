import sys
import types

import numpy as np
import pytest

from tms_vision.landmark import Landmark
from tms_vision.pose_models import (
    BasePoseModel, FramePose, Keypoint, ModelMetadata, ModelUnavailableError, PoseModelError,
    VideoUnreadableError, available_models, create_model, group_of, keypoints_to_landmarks,
    landmarks_to_keypoints, register,
)


def test_landmarks_round_trip_and_lowercase_names():
    landmarks = {"LEFT_WRIST": Landmark(0.42, 0.61, 0.03, 0.97)}
    keypoints = landmarks_to_keypoints(landmarks)
    assert keypoints[0].name == "left_wrist"
    assert keypoints[0].confidence == 0.97
    assert keypoints_to_landmarks(keypoints) == landmarks


def test_missing_landmarks_give_no_keypoints():
    assert landmarks_to_keypoints(None) == []
    assert keypoints_to_landmarks([]) == {}


def test_frame_pose_dict_format_and_round_trip():
    pose = FramePose(frame=120, model="mediapipe_pose_33",
                     keypoints=[Keypoint("left_wrist", 0.42, 0.61, 0.03, 0.94, 0.97)])
    data = pose.to_dict()
    assert data["frame"] == 120 and data["person_id"] == 1
    assert data["keypoints"][0] == {"name": "left_wrist", "x": 0.42, "y": 0.61, "z": 0.03,
                                    "confidence": 0.94, "visibility": 0.97}
    assert FramePose.from_dict(data) == pose


@pytest.mark.parametrize("name,group", [
    ("left_shoulder", "body"), ("nose", "face"), ("left_heel", "feet"),
    ("right_index_tip", "hands"), ("left_hand_wrist", "hands"), ("face_12", "face"),
    ("custom_tool", "custom"), ("right_big_toe", "feet"),
])
def test_group_of(name, group):
    assert group_of(name) == group


def test_registry_default_and_unknown_model():
    assert [m["id"] for m in available_models() if m["default"]] == ["mediapipe_pose_33"]
    assert create_model(None).get_metadata().keypoint_count == 33
    with pytest.raises(PoseModelError, match="inconnu"):
        create_model("nope")


def test_available_models_flags_missing_dependency():
    info = {m["id"]: m for m in available_models()}["mediapipe_pose_33"]
    assert info["installed"] == (__import__("importlib.util").util.find_spec("mediapipe") is not None)


def test_mediapipe_adapter_wraps_estimator(monkeypatch):
    fake = types.ModuleType("tms_vision.pose_estimation")

    class FakeEstimator:
        def __init__(self, min_visibility=0.5): pass
        def process(self, image):
            return types.SimpleNamespace(
                landmarks={"LEFT_SHOULDER": Landmark(0.1, 0.2, 0.0, 0.9)}, world_landmarks=None)
        def close(self): pass

    fake.PoseEstimator = FakeEstimator
    monkeypatch.setitem(sys.modules, "tms_vision.pose_estimation", fake)
    model = create_model("mediapipe_pose_33")
    poses = model.process_frame(np.zeros((4, 4, 3), np.uint8), frame_index=7)
    assert poses[0].frame == 7 and poses[0].keypoints[0].name == "left_shoulder"
    assert model.get_keypoints() == poses
    model.close()


def test_mediapipe_adapter_reports_missing_install(monkeypatch):
    monkeypatch.setitem(sys.modules, "tms_vision.pose_estimation", None)  # force ImportError
    with pytest.raises(ModelUnavailableError, match="mediapipe"):
        create_model("mediapipe_pose_33").load()


class _Dummy(BasePoseModel):
    metadata = ModelMetadata("dummy", "Dummy", 1, ("body",))

    def load(self): pass

    def process_frame(self, frame, frame_index=0):
        return [FramePose(frame_index, "dummy", [Keypoint("nose", 0.5, 0.5)])]


def test_register_custom_model_and_unreadable_video(tmp_path):
    register("dummy", _Dummy)
    model = create_model("dummy")
    with pytest.raises(VideoUnreadableError):
        model.process_video(str(tmp_path / "absente.mp4"))
    empty = tmp_path / "vide.mp4"
    empty.write_bytes(b"")
    with pytest.raises(VideoUnreadableError):
        model.process_video(str(empty))
