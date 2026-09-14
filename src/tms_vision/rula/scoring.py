"""Moteur de scoring RULA complet : classification des angles en sous-scores
1-N, puis application des Tables A/B/C officielles (voir rula/tables.py)."""
from collections import deque
from dataclasses import dataclass

from tms_vision.angles import JointAngles
from tms_vision.rula.tables import lookup_table_a, lookup_table_b, lookup_table_c

LEGS_SCORE = 1  # Jambes supposées soutenues (limite connue du PoC, voir spec)


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))


def classify_upper_arm(angle_deg: float, shoulder_raised: bool, abducted: bool, supported: bool) -> int:
    if angle_deg < -90.0:
        # Au-delà de -90°, le signe de upper_arm_flexion_deg n'est plus fiable
        # (bruit de mesure sur un bras levé à la verticale, voir angles.py /
        # upper_arm_forward) : la magnitude (~180°) indique un bras en
        # extension/élévation extrême, à traiter avec la même sévérité RULA
        # qu'une flexion avant > 90° (base 4), pas comme une extension légère
        # (Fix I1, 2e revue finale).
        base = 4
    elif angle_deg < -20.0:
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
    if flexion_deg < -5.0:
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


STATIC_DURATION_THRESHOLD_SECONDS = 60.0
STATIC_VARIATION_THRESHOLD_DEG = 15.0
REPETITION_THRESHOLD_PER_MINUTE = 4.0
REPETITION_MIN_PROMINENCE_DEG = 10.0


def _longest_static_span_seconds(history: list[tuple[float, float]]) -> float:
    """Plus longue plage temporelle (en secondes) d'une fenêtre contiguë où
    max(angle) - min(angle) <= STATIC_VARIATION_THRESHOLD_DEG.

    Implémentation O(n) : fenêtre glissante avec deux deques monotones
    (max_deque décroissante, min_deque croissante) maintenant en O(1) amorti
    le max et le min courants de la fenêtre [window_start, end], au lieu de
    reconstruire et scanner la fenêtre à chaque étape (O(n²))."""
    longest = 0.0
    window_start = 0
    max_deque: deque[int] = deque()  # indices, valeurs décroissantes ; tête = max courant
    min_deque: deque[int] = deque()  # indices, valeurs croissantes ; tête = min courant

    for end in range(len(history)):
        angle = history[end][1]

        while max_deque and history[max_deque[-1]][1] <= angle:
            max_deque.pop()
        max_deque.append(end)

        while min_deque and history[min_deque[-1]][1] >= angle:
            min_deque.pop()
        min_deque.append(end)

        while history[max_deque[0]][1] - history[min_deque[0]][1] > STATIC_VARIATION_THRESHOLD_DEG:
            window_start += 1
            if max_deque[0] < window_start:
                max_deque.popleft()
            if min_deque[0] < window_start:
                min_deque.popleft()

        span = history[end][0] - history[window_start][0]
        longest = max(longest, span)
    return longest


def _count_direction_changes(history: list[tuple[float, float]]) -> int:
    changes = 0
    last_extremum = history[0][1]
    direction = 0
    for _, angle in history[1:]:
        delta = angle - last_extremum
        if abs(delta) < REPETITION_MIN_PROMINENCE_DEG:
            continue
        new_direction = 1 if delta > 0 else -1
        if direction != 0 and new_direction != direction:
            changes += 1
        direction = new_direction
        last_extremum = angle
    return changes


def detect_muscle_use(history: list[tuple[float, float]]) -> bool:
    """history : liste de (timestamp_secondes, angle_charge_posturale) triée par temps.
    Retourne True si la posture est majoritairement statique (>1 min sans
    variation significative) ou si le mouvement se répète >= 4 fois/minute."""
    if len(history) < 2:
        return False

    if _longest_static_span_seconds(history) >= STATIC_DURATION_THRESHOLD_SECONDS:
        return True

    duration_minutes = (history[-1][0] - history[0][0]) / 60.0
    if duration_minutes <= 0:
        return False

    direction_changes = _count_direction_changes(history)
    cycles = direction_changes / 2.0
    return (cycles / duration_minutes) >= REPETITION_THRESHOLD_PER_MINUTE
