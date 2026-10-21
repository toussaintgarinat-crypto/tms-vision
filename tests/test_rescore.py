import pytest

from tms_vision.angles import JointAngles
from tms_vision.rescore import rescore_frames, summarize_for_load
from tms_vision.rula.scoring import compute_rula_score


def _angles(**overrides):
    base = dict(
        neck_flexion_deg=5.0, neck_twisted=False, neck_side_bending=False,
        trunk_flexion_deg=1.0, trunk_twisted=False, trunk_side_bending=False,
        upper_arm_flexion_deg=10.0, upper_arm_abducted=False, upper_arm_shoulder_raised=False,
        lower_arm_angle_deg=90.0, lower_arm_across_midline=False,
        wrist_flexion_deg=0.5, wrist_bent_from_midline=False, arm_supported=False,
    )
    base.update(overrides)
    return JointAngles(**base)


POSTURES = {
    "neutral": _angles(),
    "bent_trunk": _angles(trunk_flexion_deg=70.0, trunk_twisted=True, neck_flexion_deg=35.0),
    "raised_arm": _angles(
        upper_arm_flexion_deg=100.0, upper_arm_abducted=True, lower_arm_angle_deg=130.0,
        wrist_flexion_deg=20.0,
    ),
}
LOADS = [0.0, 1.9, 2.0, 5.0, 10.0, 10.1, 25.0]


def _stored_frame(index, score, detected=True):
    """Ce que analysis_frames persiste d'un score : seulement les sous-scores
    dont le recalcul a besoin."""
    return {
        "frame_index": index,
        "timestamp_seconds": float(index),
        "detected": detected,
        "posture_score_a": score.posture_score_a if score else None,
        "posture_score_b": score.posture_score_b if score else None,
        "muscle_use_score": score.muscle_use_score if score else None,
    }


@pytest.mark.parametrize("posture_name", POSTURES)
@pytest.mark.parametrize("muscle_use", [0, 1])
@pytest.mark.parametrize("original_load", [0.0, 5.0, 25.0])
@pytest.mark.parametrize("new_load", LOADS)
def test_rescore_reproduces_compute_rula_score_exactly(
    posture_name, muscle_use, original_load, new_load
):
    angles = POSTURES[posture_name]
    original = compute_rula_score(angles, wrist_twist=1, load_kg=original_load, muscle_use_score=muscle_use)
    expected = compute_rula_score(angles, wrist_twist=1, load_kg=new_load, muscle_use_score=muscle_use)

    rescored = rescore_frames([_stored_frame(0, original)], new_load)[0]

    assert rescored["force_load_score"] == expected.force_load_score
    assert rescored["final_score"] == expected.final_score
    assert rescored["action_level"] == expected.action_level


def test_a_heavy_load_raises_the_score_without_touching_posture_scores():
    angles = POSTURES["bent_trunk"]
    at_zero = compute_rula_score(angles, wrist_twist=1, load_kg=0.0, muscle_use_score=0)

    heavy = rescore_frames([_stored_frame(0, at_zero)], 25.0)[0]

    assert heavy["final_score"] > at_zero.final_score
    assert heavy["posture_score_a"] == at_zero.posture_score_a
    assert heavy["posture_score_b"] == at_zero.posture_score_b


def test_frame_without_score_stays_without_score():
    rescored = rescore_frames([_stored_frame(0, None, detected=False)], 12.0)[0]

    assert rescored["force_load_score"] is None
    assert rescored["final_score"] is None
    assert rescored["action_level"] is None


def test_rescore_does_not_mutate_its_input():
    score = compute_rula_score(POSTURES["neutral"], wrist_twist=1, load_kg=0.0, muscle_use_score=0)
    frames = [_stored_frame(0, score)]

    rescore_frames(frames, 25.0)

    assert "final_score" not in frames[0]


def test_summarize_for_load_matches_a_manual_computation():
    score = compute_rula_score(POSTURES["bent_trunk"], wrist_twist=1, load_kg=0.0, muscle_use_score=0)
    frames = [
        _stored_frame(0, score),
        _stored_frame(1, None, detected=False),
        _stored_frame(2, score),
    ]
    expected_final = compute_rula_score(
        POSTURES["bent_trunk"], wrist_twist=1, load_kg=15.0, muscle_use_score=0
    )

    summary = summarize_for_load(frames, 15.0)

    assert summary["frame_count"] == 3
    assert summary["detected_frame_count"] == 2
    assert summary["max_score"] == expected_final.final_score
    assert summary["average_score"] == float(expected_final.final_score)
    # frame 0 dure jusqu'a la frame suivante de la sequence (non detectee, t=1) : 1 s ;
    # frame 2 est la derniere -> 0 s.
    assert summary["time_by_action_level"] == {expected_final.action_level: 1.0}


def test_summarize_for_load_with_nothing_detected_is_empty():
    summary = summarize_for_load([_stored_frame(0, None, detected=False)], 10.0)

    assert summary["detected_frame_count"] == 0
    assert summary["max_score"] == 0
    assert summary["time_by_action_level"] == {}
