# tests/test_overlay.py
import numpy as np
from tms_vision.overlay import action_level_color, draw_overlay
from tms_vision.rula.scoring import RulaScore


def _score(final_score, level):
    return RulaScore(
        upper_arm=1, lower_arm=1, wrist=1, wrist_twist=1, posture_score_a=1,
        neck=1, trunk=1, legs=1, posture_score_b=1, muscle_use_score=0,
        force_load_score=0, wrist_arm_score=1, neck_trunk_leg_score=1,
        final_score=final_score, action_level=level,
    )


def test_action_level_color_acceptable_is_green():
    b, g, r = action_level_color("acceptable")
    assert g > r and g > b


def test_action_level_color_immediate_change_is_red():
    b, g, r = action_level_color("changement_immediat")
    assert r > g and r > b


def test_draw_overlay_returns_new_array_without_mutating_input():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    result = draw_overlay(frame, landmarks=None, score=_score(1, "acceptable"))

    assert result is not frame
    assert result.shape == frame.shape
    assert np.any(result != frame)  # le badge a bien été dessiné


def test_draw_overlay_with_no_landmarks_and_no_score_returns_unmodified_copy():
    frame = np.zeros((50, 50, 3), dtype=np.uint8)
    result = draw_overlay(frame, landmarks=None, score=None)

    assert np.array_equal(result, frame)
