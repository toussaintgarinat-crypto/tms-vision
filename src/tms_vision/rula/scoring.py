"""Moteur de scoring RULA complet : classification des angles en sous-scores
1-N, puis application des Tables A/B/C officielles (voir rula/tables.py)."""
from dataclasses import dataclass

from tms_vision.angles import JointAngles
from tms_vision.rula.tables import lookup_table_a, lookup_table_b, lookup_table_c

LEGS_SCORE = 1  # Jambes supposées soutenues (limite connue du PoC, voir spec)


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))


def classify_upper_arm(angle_deg: float, shoulder_raised: bool, abducted: bool, supported: bool) -> int:
    if angle_deg < -20.0:
        base = 2
    elif angle_deg <= 20.0:
        base = 1
    elif angle_deg <= 45.0:
        base = 2
    elif angle_deg <= 90.0:
        base = 3
    else:
        base = 4

    score = base + (1 if shoulder_raised else 0) + (1 if abducted else 0) - (1 if supported else 0)
    return _clamp(score, 1, 6)


def classify_lower_arm(angle_deg: float, across_midline: bool) -> int:
    base = 1 if 60.0 <= angle_deg <= 100.0 else 2
    score = base + (1 if across_midline else 0)
    return _clamp(score, 1, 3)


def classify_wrist(flexion_deg: float, bent_from_midline: bool) -> int:
    magnitude = abs(flexion_deg)
    if magnitude <= 2.0:
        base = 1
    elif magnitude <= 15.0:
        base = 2
    else:
        base = 3
    score = base + (1 if bent_from_midline else 0)
    return _clamp(score, 1, 4)


def classify_neck(flexion_deg: float, twisted: bool, side_bending: bool) -> int:
    if flexion_deg < 0:
        base = 4
    elif flexion_deg <= 10.0:
        base = 1
    elif flexion_deg <= 20.0:
        base = 2
    else:
        base = 3

    score = base + (1 if twisted else 0) + (1 if side_bending else 0)
    return _clamp(score, 1, 6)


def classify_trunk(flexion_deg: float, twisted: bool, side_bending: bool) -> int:
    if flexion_deg <= 2.0:
        base = 1
    elif flexion_deg <= 20.0:
        base = 2
    elif flexion_deg <= 60.0:
        base = 3
    else:
        base = 4

    score = base + (1 if twisted else 0) + (1 if side_bending else 0)
    return _clamp(score, 1, 6)


def force_load_score(load_kg: float, is_static_or_repetitive: bool) -> int:
    if load_kg < 2.0:
        return 0
    if load_kg <= 10.0:
        return 2 if is_static_or_repetitive else 1
    return 3


def action_level(final_score: int) -> str:
    if final_score <= 2:
        return "acceptable"
    if final_score <= 4:
        return "investigation_recommandee"
    if final_score <= 6:
        return "investigation_et_changement_bientot"
    return "changement_immediat"


@dataclass
class RulaScore:
    upper_arm: int
    lower_arm: int
    wrist: int
    wrist_twist: int
    posture_score_a: int
    neck: int
    trunk: int
    legs: int
    posture_score_b: int
    muscle_use_score: int
    force_load_score: int
    wrist_arm_score: int
    neck_trunk_leg_score: int
    final_score: int
    action_level: str


def compute_rula_score(
    angles: JointAngles, wrist_twist: int, load_kg: float, muscle_use_score: int
) -> RulaScore:
    upper_arm = classify_upper_arm(
        angles.upper_arm_flexion_deg,
        angles.upper_arm_shoulder_raised,
        angles.upper_arm_abducted,
        angles.arm_supported,
    )
    lower_arm = classify_lower_arm(angles.lower_arm_angle_deg, angles.lower_arm_across_midline)
    wrist = classify_wrist(angles.wrist_flexion_deg, angles.wrist_bent_from_midline)
    neck = classify_neck(angles.neck_flexion_deg, angles.neck_twisted, angles.neck_side_bending)
    trunk = classify_trunk(angles.trunk_flexion_deg, angles.trunk_twisted, angles.trunk_side_bending)

    posture_score_a = lookup_table_a(upper_arm, lower_arm, wrist, wrist_twist)
    posture_score_b = lookup_table_b(neck, trunk, LEGS_SCORE)

    is_static_or_repetitive = muscle_use_score == 1
    force_score = force_load_score(load_kg, is_static_or_repetitive)

    wrist_arm_score = posture_score_a + muscle_use_score + force_score
    neck_trunk_leg_score = posture_score_b + muscle_use_score + force_score

    final_score = lookup_table_c(wrist_arm_score, neck_trunk_leg_score)

    return RulaScore(
        upper_arm=upper_arm,
        lower_arm=lower_arm,
        wrist=wrist,
        wrist_twist=wrist_twist,
        posture_score_a=posture_score_a,
        neck=neck,
        trunk=trunk,
        legs=LEGS_SCORE,
        posture_score_b=posture_score_b,
        muscle_use_score=muscle_use_score,
        force_load_score=force_score,
        wrist_arm_score=wrist_arm_score,
        neck_trunk_leg_score=neck_trunk_leg_score,
        final_score=final_score,
        action_level=action_level(final_score),
    )
