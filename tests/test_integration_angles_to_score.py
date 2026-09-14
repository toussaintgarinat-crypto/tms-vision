"""Test de régression bout-en-bout : landmarks -> angles -> score RULA.

Ce test aurait immédiatement détecté le bug de convention d'angles (Fix 1
de la revue finale) : une posture debout, de profil, neutre (bras pendant,
poignet droit) doit produire un score RULA final <= 2 ("acceptable"), pas
un score élevé causé par une mauvaise convention de signe/référence sur
upper_arm_flexion_deg ou wrist_flexion_deg.
"""
from tms_vision.pose_estimation import Landmark
from tms_vision.angles import compute_joint_angles
from tms_vision.rula.scoring import (
    compute_rula_score,
    classify_upper_arm,
    classify_wrist,
    classify_lower_arm,
)


def _lm(x, y, z=0.0, visibility=1.0):
    return Landmark(x=x, y=y, z=z, visibility=visibility)


def _neutral_standing_landmarks():
    """Personne debout, de profil, tournée vers +x, posture neutre :
    bras pendant le long du corps, poignet droit, tête et tronc alignés."""
    return {
        "LEFT_SHOULDER": _lm(0.50, 0.30),
        "RIGHT_SHOULDER": _lm(0.50, 0.30),
        "LEFT_HIP": _lm(0.50, 0.55),
        "RIGHT_HIP": _lm(0.50, 0.55),
        "NOSE": _lm(0.52, 0.20),
        "LEFT_EAR": _lm(0.51, 0.22),
        "RIGHT_EAR": _lm(0.51, 0.22),
        "LEFT_ELBOW": _lm(0.50, 0.45),
        "LEFT_WRIST": _lm(0.50, 0.60),
        "LEFT_INDEX": _lm(0.50, 0.63),
    }


def test_neutral_standing_posture_scores_acceptable_end_to_end():
    landmarks = _neutral_standing_landmarks()
    angles = compute_joint_angles(landmarks, side="left")
    assert angles is not None

    score = compute_rula_score(
        angles, wrist_twist=1, load_kg=0.0, muscle_use_score=0
    )

    assert score.upper_arm == 1, f"upper_arm should be 1 (neutral), got {score.upper_arm}"
    assert score.wrist == 1, f"wrist should be 1 (neutral), got {score.wrist}"
    assert score.final_score <= 2
    assert score.action_level == "acceptable"


def test_upper_arm_reaching_90_degrees_forward_is_classified_base_3():
    # Fix I2 (2e revue finale) : le test de neutralité ci-dessus n'aurait pas
    # détecté un bug qui inverserait/décalerait uniquement la PENTE de
    # upper_arm_flexion_deg tout en laissant le point neutre (bras pendant)
    # à ~0°. On épingle donc ici un point non-neutre dans la convention
    # CORRIGÉE par Fix 1 : coude déplacé à l'horizontale devant l'épaule
    # (facing=+1, cf. NOSE.x >= shoulder_mid.x), ce qui doit donner
    # upper_arm_vec = elbow - shoulder = (0.15, 0.0), perpendiculaire à
    # "downward" = (0, 1) -> magnitude 90°, et upper_arm_forward =
    # (elbow.x - shoulder.x) * facing = 0.15 > 0 -> signe positif conservé.
    landmarks = _neutral_standing_landmarks()
    landmarks["LEFT_ELBOW"] = _lm(0.65, 0.30)
    landmarks["LEFT_WRIST"] = _lm(0.80, 0.30)
    landmarks["LEFT_INDEX"] = _lm(0.83, 0.30)

    angles = compute_joint_angles(landmarks, side="left")
    assert angles is not None
    assert 85.0 <= angles.upper_arm_flexion_deg <= 95.0, angles.upper_arm_flexion_deg

    base = classify_upper_arm(
        angles.upper_arm_flexion_deg,
        shoulder_raised=angles.upper_arm_shoulder_raised,
        abducted=angles.upper_arm_abducted,
        supported=angles.arm_supported,
    )
    assert base == 3, f"upper_arm base should be 3 (45-90° band), got {base}"


def test_wrist_bent_30_degrees_is_classified_base_3():
    # Coude/poignet inchangés (bras tendu vers le bas), mais l'index est
    # placé de façon à ce que hand_vec (poignet -> index) fasse ~30° avec
    # forearm_vec (coude -> poignet) = (0, 0.15). hand_vec = (0.015,
    # 0.02598) (rotation de 30° de (0, 0.15) normalisé, longueur 0.03) :
    # angle_between donne bien ~30° par construction trigonométrique.
    landmarks = _neutral_standing_landmarks()
    landmarks["LEFT_INDEX"] = _lm(0.515, 0.62598)

    angles = compute_joint_angles(landmarks, side="left")
    assert angles is not None
    assert 25.0 <= angles.wrist_flexion_deg <= 35.0, angles.wrist_flexion_deg

    base = classify_wrist(angles.wrist_flexion_deg, bent_from_midline=angles.wrist_bent_from_midline)
    assert base == 3, f"wrist base should be 3 (>15° band), got {base}"


def test_elbow_bent_90_degrees_is_classified_base_1():
    # Bras supérieur vertical (épaule au-dessus du coude, upper_arm_from_elbow
    # = shoulder - elbow = (0, -0.15)), avant-bras horizontal (forearm_vec =
    # wrist - elbow = (0.15, 0)) : les deux vecteurs sont perpendiculaires par
    # construction -> angle_between = 90° -> lower_arm_angle_deg =
    # 180 - 90 = 90° (flexion-depuis-tendu), dans la bande RULA 60-100°.
    landmarks = _neutral_standing_landmarks()
    landmarks["LEFT_ELBOW"] = _lm(0.50, 0.45)
    landmarks["LEFT_WRIST"] = _lm(0.65, 0.45)
    landmarks["LEFT_INDEX"] = _lm(0.68, 0.45)

    angles = compute_joint_angles(landmarks, side="left")
    assert angles is not None
    assert 85.0 <= angles.lower_arm_angle_deg <= 95.0, angles.lower_arm_angle_deg

    base = classify_lower_arm(angles.lower_arm_angle_deg, across_midline=angles.lower_arm_across_midline)
    assert base == 1, f"lower_arm base should be 1 (60-100° band), got {base}"
