from tms_vision.angles import JointAngles
from tms_vision.rula.scoring import (
    classify_upper_arm,
    classify_lower_arm,
    classify_wrist,
    classify_neck,
    classify_trunk,
    force_load_score,
    action_level,
    compute_rula_score,
)


def test_classify_upper_arm_neutral_is_score_1():
    assert classify_upper_arm(10.0, shoulder_raised=False, abducted=False, supported=False) == 1


def test_classify_upper_arm_extension_beyond_20_is_score_2():
    assert classify_upper_arm(-25.0, shoulder_raised=False, abducted=False, supported=False) == 2


def test_classify_upper_arm_flexion_90_plus_is_score_4():
    assert classify_upper_arm(95.0, shoulder_raised=False, abducted=False, supported=False) == 4


def test_classify_upper_arm_adjustments_add_up_and_clamp_at_6():
    assert classify_upper_arm(95.0, shoulder_raised=True, abducted=True, supported=False) == 6


def test_classify_upper_arm_supported_subtracts_one():
    assert classify_upper_arm(10.0, shoulder_raised=False, abducted=False, supported=True) == 1


def test_classify_lower_arm_90_degrees_is_score_1():
    assert classify_lower_arm(90.0, across_midline=False) == 1


def test_classify_lower_arm_straight_arm_is_score_2():
    assert classify_lower_arm(175.0, across_midline=False) == 2


def test_classify_wrist_neutral_is_score_1():
    assert classify_wrist(0.5, bent_from_midline=False) == 1


def test_classify_wrist_15_plus_degrees_is_score_3():
    assert classify_wrist(20.0, bent_from_midline=False) == 3


def test_classify_neck_0_to_10_is_score_1():
    assert classify_neck(5.0, twisted=False, side_bending=False) == 1


def test_classify_neck_extension_is_score_4():
    assert classify_neck(-5.0, twisted=False, side_bending=False) == 4


def test_classify_trunk_upright_is_score_1():
    assert classify_trunk(1.0, twisted=False, side_bending=False) == 1


def test_classify_trunk_60_plus_is_score_4():
    assert classify_trunk(70.0, twisted=False, side_bending=False) == 4


def test_force_load_under_2kg_is_score_0():
    assert force_load_score(1.5, is_static_or_repetitive=True) == 0


def test_force_load_2_to_10kg_intermittent_is_score_1():
    assert force_load_score(5.0, is_static_or_repetitive=False) == 1


def test_force_load_2_to_10kg_static_is_score_2():
    assert force_load_score(5.0, is_static_or_repetitive=True) == 2


def test_force_load_over_10kg_is_score_3():
    assert force_load_score(15.0, is_static_or_repetitive=False) == 3


def test_action_level_matches_readme_matrix():
    assert action_level(1) == "acceptable"
    assert action_level(2) == "acceptable"
    assert action_level(3) == "investigation_recommandee"
    assert action_level(4) == "investigation_recommandee"
    assert action_level(5) == "investigation_et_changement_bientot"
    assert action_level(6) == "investigation_et_changement_bientot"
    assert action_level(7) == "changement_immediat"


def _neutral_angles(**overrides):
    base = dict(
        neck_flexion_deg=5.0,
        neck_twisted=False,
        neck_side_bending=False,
        trunk_flexion_deg=1.0,
        trunk_twisted=False,
        trunk_side_bending=False,
        upper_arm_flexion_deg=10.0,
        upper_arm_abducted=False,
        upper_arm_shoulder_raised=False,
        lower_arm_angle_deg=90.0,
        lower_arm_across_midline=False,
        wrist_flexion_deg=0.5,
        wrist_bent_from_midline=False,
        arm_supported=False,
    )
    base.update(overrides)
    return JointAngles(**base)


def test_compute_rula_score_neutral_posture_is_low_risk():
    score = compute_rula_score(
        _neutral_angles(), wrist_twist=1, load_kg=0.0, muscle_use_score=0
    )
    assert score.final_score <= 2
    assert score.action_level == "acceptable"
    assert score.legs == 1


def test_compute_rula_score_high_risk_posture():
    score = compute_rula_score(
        _neutral_angles(
            upper_arm_flexion_deg=95.0,
            upper_arm_abducted=True,
            trunk_flexion_deg=70.0,
            trunk_twisted=True,
            neck_flexion_deg=25.0,
        ),
        wrist_twist=2,
        load_kg=15.0,
        muscle_use_score=1,
    )
    assert score.final_score >= 6


from tms_vision.rula.scoring import detect_muscle_use, _longest_static_span_seconds


def test_longest_static_span_ignores_volatile_prefix_and_tail():
    # Préfixe volatile (indices 0-1), puis une plage statique de 7 échantillons
    # (indices 2-8, valeurs toutes dans [10, 25], amplitude 15 <= seuil),
    # puis une queue volatile (index 9). La plage la plus longue ne doit ni
    # commencer à l'index 0 ni couvrir tout l'historique : elle doit
    # correspondre exactement à la plage statique du milieu.
    history = [
        (0.0, 0.0),
        (1.0, 90.0),
        (2.0, 10.0),
        (3.0, 25.0),
        (4.0, 10.0),
        (5.0, 25.0),
        (6.0, 10.0),
        (7.0, 25.0),
        (8.0, 18.0),
        (9.0, 200.0),
    ]
    # Calculé à la main : la fenêtre [2..8] a max=25, min=10 (amplitude 15,
    # au seuil), pour une plage de 8.0 - 2.0 = 6.0 secondes. Toute fenêtre
    # incluant l'index 1 (90.0) ou l'index 9 (200.0) dépasse le seuil.
    assert _longest_static_span_seconds(history) == 6.0


def test_detect_muscle_use_static_posture_over_one_minute():
    history = [(float(t), 45.0) for t in range(0, 65, 1)]  # angle constant 65s
    assert detect_muscle_use(history) is True


def test_detect_muscle_use_short_clip_with_no_repetition_is_false():
    history = [(float(t), 45.0 + t) for t in range(0, 20, 1)]  # < 1 min, monotonic
    assert detect_muscle_use(history) is False


def test_detect_muscle_use_repetitive_motion_over_4_cycles_per_minute():
    # Oscillation triangulaire : 8 cycles complets sur 60 secondes -> 8/min >= 4/min
    history = []
    for t in range(0, 60):
        phase = t % 7.5
        angle = 20.0 + (20.0 if phase < 3.75 else -20.0)
        history.append((float(t), angle))
    assert detect_muscle_use(history) is True
