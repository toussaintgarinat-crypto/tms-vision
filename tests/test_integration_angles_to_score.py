"""Test de régression bout-en-bout : landmarks -> angles -> score RULA.

Ce test aurait immédiatement détecté le bug de convention d'angles (Fix 1
de la revue finale) : une posture debout, de profil, neutre (bras pendant,
poignet droit) doit produire un score RULA final <= 2 ("acceptable"), pas
un score élevé causé par une mauvaise convention de signe/référence sur
upper_arm_flexion_deg ou wrist_flexion_deg.
"""
from tms_vision.pose_estimation import Landmark
from tms_vision.angles import compute_joint_angles
from tms_vision.rula.scoring import compute_rula_score


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
