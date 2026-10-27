import sys
import types

import numpy as np

from tms_vision.extremities import load_extremity_thresholds
from tms_vision.hand_metrics import GripAccumulator, finger_curl_from_keypoints
from tms_vision.landmark import Landmark
from tms_vision.overlay import draw_overlay
from tms_vision.pose_models import Keypoint, group_of
from tms_vision.pose_models.mediapipe_hands import (
    HAND_CONNECTIONS, HAND_POINT_SUFFIXES, MediaPipeHandsModel, hand_point_names,
)


def hand_keypoints(side: str, curl_deg: float) -> list[Keypoint]:
    """21 points : doigts longs pliés de `curl_deg` à l'articulation médiane (0 = tendu)."""
    theta = np.radians(curl_deg)
    points = {name: (0.5, 0.8) for name in hand_point_names(side)}
    for finger_index, finger in enumerate(("index", "middle", "ring", "pinky")):
        x = 0.4 + 0.05 * finger_index
        points[f"{side}_{finger}_mcp"] = (x, 0.6)
        points[f"{side}_{finger}_pip"] = (x, 0.5)
        points[f"{side}_{finger}_dip"] = (x + 0.1 * np.sin(theta), 0.5 - 0.1 * np.cos(theta))
        points[f"{side}_{finger}_tip"] = points[f"{side}_{finger}_dip"]
    return [Keypoint(name, x, y) for name, (x, y) in points.items()]


def test_hand_point_names_cover_21_distinct_points_in_hands_group():
    names = hand_point_names("right")
    assert len(set(names)) == 21 and len(HAND_POINT_SUFFIXES) == 21
    assert "right_index_tip" in names and "right_hand_wrist" in names
    assert {group_of(n) for n in names} == {"hands"}
    assert len(HAND_CONNECTIONS) == 20


def test_finger_curl_from_keypoints_matches_geometry_and_needs_all_points():
    assert abs(finger_curl_from_keypoints(hand_keypoints("right", 0), "right") - 0) < 1
    assert abs(finger_curl_from_keypoints(hand_keypoints("right", 90), "right") - 90) < 1
    assert finger_curl_from_keypoints(hand_keypoints("right", 90)[:10], "right") is None
    assert finger_curl_from_keypoints(hand_keypoints("right", 90), "left") is None


def _grips(curls, step=0.1):
    acc = GripAccumulator(load_extremity_thresholds())
    for i, curl in enumerate(curls):
        acc.update(i * step, curl)
    return acc.summary()


def test_grasp_counted_once_despite_oscillation_around_threshold():
    # 70° = seuil d'entrée ; 65° est dans l'hystérésis (sortie sous 60°) : une seule préhension.
    summary = _grips([10, 80, 65, 75, 80, 40, 10])
    assert summary["grasp_count"] == 1
    assert summary["finger_curl_max_deg"] == 80


def test_two_grasps_and_their_duration():
    summary = _grips([10, 90, 90, 10, 10, 90, 90, 90, 10])
    assert summary["grasp_count"] == 2
    assert abs(summary["grasp_seconds"] - 0.5) < 1e-6


def test_missing_detection_ends_grasp_after_a_gap_and_is_not_an_error():
    summary = _grips([90, None, None, None, None, None, None, 90])  # trou de 0,6 s
    assert summary["grasp_count"] == 2
    assert summary["detection_ratio"] == 0.25


def test_no_detection_at_all_gives_empty_summary():
    summary = _grips([None, None, None])
    assert summary["grasp_count"] == 0 and summary["finger_curl_mean_deg"] is None
    assert summary["repetitive"] is False


def test_repetitive_flag_from_grasp_rate():
    curls = [10, 90] * 40  # 40 préhensions en 7,9 s : bien au-delà de 30 par minute
    assert _grips(curls)["repetitive"] is True
    short = _grips([10, 90, 10])  # 0,2 s : pas de cadence calculable
    assert short["grasps_per_minute"] is None and short["repetitive"] is False


def test_overlay_draws_hands_only_when_given():
    image = np.zeros((100, 100, 3), np.uint8)
    plain = draw_overlay(image, None, None)
    with_hands = draw_overlay(image, None, None, extra_keypoints=hand_keypoints("right", 30))
    assert plain.sum() == 0 and with_hands.sum() > 0
    assert draw_overlay(image, None, None, extra_keypoints=[]).sum() == 0


def _fake_mediapipe(monkeypatch, hands):
    """`hands` : liste de (wrist_x, wrist_y, étiquette MediaPipe) ; 21 points chacune."""
    def hand_landmarks(wx, wy):
        pts = [types.SimpleNamespace(x=wx + 0.001 * i, y=wy, z=0.0) for i in range(21)]
        return types.SimpleNamespace(landmark=pts)

    class FakeHands:
        def __init__(self, **kwargs): pass
        def process(self, rgb):
            if not hands:
                return types.SimpleNamespace(multi_hand_landmarks=None, multi_handedness=None)
            return types.SimpleNamespace(
                multi_hand_landmarks=[hand_landmarks(x, y) for x, y, _ in hands],
                multi_handedness=[
                    types.SimpleNamespace(classification=[types.SimpleNamespace(label=lab, score=0.9)])
                    for _, _, lab in hands
                ],
            )
        def close(self): pass

    mp = types.ModuleType("mediapipe")
    mp.solutions = types.SimpleNamespace(hands=types.SimpleNamespace(Hands=FakeHands))
    monkeypatch.setitem(sys.modules, "mediapipe", mp)


def test_hands_model_assigns_sides_by_proximity_to_pose_wrists(monkeypatch):
    # Étiquettes MediaPipe volontairement « fausses » : seule la proximité compte avec Pose.
    _fake_mediapipe(monkeypatch, [(0.30, 0.50, "Left"), (0.70, 0.50, "Right")])
    model = MediaPipeHandsModel()
    poses = model.process_frame(
        np.zeros((100, 100, 3), np.uint8), 4,
        pose_wrists={"left": Landmark(0.7, 0.5, 0, 1), "right": Landmark(0.3, 0.5, 0, 1)},
    )
    by_name = poses[0].by_name()
    assert len(poses[0].keypoints) == 42 and poses[0].frame == 4
    assert abs(by_name["right_hand_wrist"].x - 0.30) < 1e-6
    assert abs(by_name["left_hand_wrist"].x - 0.70) < 1e-6


def test_hands_model_ignores_hand_far_from_any_pose_wrist(monkeypatch):
    _fake_mediapipe(monkeypatch, [(0.9, 0.9, "Left")])
    model = MediaPipeHandsModel()
    poses = model.process_frame(
        np.zeros((100, 100, 3), np.uint8), 0, pose_wrists={"right": Landmark(0.1, 0.1, 0, 1)}
    )
    assert poses == []


def test_hands_model_without_pose_uses_mirrored_label_and_handles_no_hand(monkeypatch):
    _fake_mediapipe(monkeypatch, [(0.3, 0.5, "Left")])
    poses = MediaPipeHandsModel().process_frame(np.zeros((50, 50, 3), np.uint8))
    assert "right_hand_wrist" in poses[0].by_name()
    _fake_mediapipe(monkeypatch, [])
    assert MediaPipeHandsModel().process_frame(np.zeros((50, 50, 3), np.uint8)) == []
