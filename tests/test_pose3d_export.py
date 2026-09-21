import json
import random

import pytest

from tms_vision.pose_estimation import Landmark
from tms_vision.pose3d_export import Pose3DFrameRecord, smooth_world_landmarks, write_pose3d_json


def test_smooth_world_landmarks_keeps_constant_sequence_unchanged():
    frame = {"NOSE": Landmark(x=1.0, y=2.0, z=3.0, visibility=0.9)}
    frames = [frame, frame, frame, frame, frame]

    smoothed = smooth_world_landmarks(frames, window=5)

    for result in smoothed:
        assert result["NOSE"].x == pytest.approx(1.0)
        assert result["NOSE"].y == pytest.approx(2.0)
        assert result["NOSE"].z == pytest.approx(3.0)


def test_smooth_world_landmarks_keeps_none_frames_none():
    detected = {"NOSE": Landmark(x=0.0, y=0.0, z=0.0, visibility=0.9)}
    frames = [detected, None, detected]

    smoothed = smooth_world_landmarks(frames, window=3)

    assert smoothed[1] is None
    assert smoothed[0] is not None
    assert smoothed[2] is not None


def test_smooth_world_landmarks_reduces_noise_variance():
    random.seed(0)
    raw_xs = [1.0 + random.uniform(-0.1, 0.1) for _ in range(20)]
    frames = [{"NOSE": Landmark(x=x, y=0.0, z=0.0, visibility=0.9)} for x in raw_xs]

    smoothed = smooth_world_landmarks(frames, window=5)
    smoothed_xs = [f["NOSE"].x for f in smoothed]

    def variance(values):
        mean = sum(values) / len(values)
        return sum((v - mean) ** 2 for v in values) / len(values)

    assert variance(smoothed_xs) < variance(raw_xs)


def test_write_pose3d_json_writes_one_entry_per_frame(tmp_path):
    path = tmp_path / "pose3d.json"
    records = [
        Pose3DFrameRecord(
            0,
            0.0,
            True,
            {"NOSE": Landmark(0.1, 0.2, 0.3, 0.9)},
            "acceptable",
            {"neck": "acceptable", "trunk": "investigation_recommandee", "upper_arm": "acceptable", "lower_arm": "acceptable"},
        ),
        Pose3DFrameRecord(1, 1.0, False, None, None, None),
    ]

    write_pose3d_json(str(path), records)

    data = json.loads(path.read_text())
    assert len(data) == 2
    assert data[0]["frame_index"] == 0
    assert data[0]["detected"] is True
    assert data[0]["landmarks"]["NOSE"] == [0.1, 0.2, 0.3]
    assert data[0]["action_level"] == "acceptable"
    assert data[0]["segment_action_levels"] == {
        "neck": "acceptable",
        "trunk": "investigation_recommandee",
        "upper_arm": "acceptable",
        "lower_arm": "acceptable",
    }
    assert data[1]["landmarks"] is None
    assert data[1]["action_level"] is None
    assert data[1]["segment_action_levels"] is None
