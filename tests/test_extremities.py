import json

import pytest

from tms_vision.angles import compute_ankle_flexion
from tms_vision.extremities import (
    classify_foot,
    classify_hand,
    extremity_action_level,
    finger_curl_deg,
    load_extremity_thresholds,
)
from tms_vision.pose_estimation import Landmark


def _lm(x, y):
    return Landmark(x=x, y=y, z=0.0, visibility=1.0)


def _leg(toes_x, toes_y):
    """Jambe verticale du genou (0.5, 0.4) à la cheville (0.5, 0.7) ; talon sous la cheville."""
    return {
        "RIGHT_KNEE": _lm(0.5, 0.4), "RIGHT_ANKLE": _lm(0.5, 0.7),
        "RIGHT_HEEL": _lm(0.45, 0.75), "RIGHT_FOOT_INDEX": _lm(toes_x, toes_y),
    }


def test_ankle_is_zero_at_right_angle():
    assert compute_ankle_flexion(_leg(0.65, 0.75), "right") == pytest.approx(0.0, abs=1e-6)


def test_ankle_is_positive_when_toes_point_down_and_negative_when_raised():
    assert compute_ankle_flexion(_leg(0.6, 0.9), "right") > 20
    assert compute_ankle_flexion(_leg(0.6, 0.6), "right") < -20


def test_ankle_is_none_when_a_landmark_is_missing():
    landmarks = _leg(0.65, 0.75)
    del landmarks["RIGHT_HEEL"]
    assert compute_ankle_flexion(landmarks, "right") is None


def _hand(curl_deg):
    """21 points : doigts longs alignés en colonne, replié à l'articulation médiane de `curl_deg`."""
    import math

    points = [(0.5, 0.9)] * 21
    for finger, base_x in enumerate((0.40, 0.46, 0.52, 0.58)):
        mcp, pip_, dip = 5 + 4 * finger, 6 + 4 * finger, 7 + 4 * finger
        points[mcp] = (base_x, 0.6)
        points[pip_] = (base_x, 0.5)
        angle = math.radians(curl_deg)
        points[dip] = (base_x + 0.1 * math.sin(angle), 0.5 - 0.1 * math.cos(angle))
    return points


def test_straight_fingers_have_no_curl():
    assert finger_curl_deg(_hand(0)) == pytest.approx(0.0, abs=1e-6)


def test_curled_fingers_are_measured():
    assert finger_curl_deg(_hand(80)) == pytest.approx(80.0, abs=1e-6)


def test_finger_curl_needs_21_points():
    assert finger_curl_deg([(0.0, 0.0)] * 20) is None


def test_hand_score_is_the_worst_of_wrist_and_fingers():
    thresholds = load_extremity_thresholds()
    assert classify_hand(0.0, 0.0, thresholds) == 1
    assert classify_hand(10.0, 0.0, thresholds) == 2
    assert classify_hand(0.0, 90.0, thresholds) == 2
    assert classify_hand(30.0, 10.0, thresholds) == 3
    assert classify_hand(0.0, 120.0, thresholds) == 3
    assert classify_hand(None, 120.0, thresholds) == 3
    assert classify_hand(None, None, thresholds) is None


def test_foot_score_follows_ankle_bounds_on_either_side():
    thresholds = load_extremity_thresholds()
    assert [classify_foot(d, thresholds) for d in (0, 10, 15, -15, 25, -40)] == [1, 1, 2, 2, 3, 3]
    assert classify_foot(None, thresholds) is None


def test_levels_follow_cutoffs_and_none_stays_none():
    thresholds = load_extremity_thresholds()
    levels = [extremity_action_level("hand", score, thresholds) for score in (1, 2, 3)]
    assert levels == [
        "acceptable", "investigation_recommandee", "investigation_et_changement_bientot",
    ]
    assert extremity_action_level("foot", None, thresholds) is None


def test_defaults_are_flagged_as_not_calibrated():
    assert load_extremity_thresholds()["calibrated"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["hand"].update(finger_curl_bounds_deg=[100.0, 70.0]),
        lambda d: d["foot"].update(level_cutoffs=[3, 2, 1]),
        lambda d: d.pop("foot"),
    ],
)
def test_invalid_thresholds_are_rejected(tmp_path, mutation):
    data = json.loads(open(load_path()).read())
    mutation(data)
    path = tmp_path / "t.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_extremity_thresholds(path)


def load_path():
    from tms_vision.extremities import THRESHOLDS_PATH

    return THRESHOLDS_PATH
