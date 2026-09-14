import math
from tms_vision.pose_estimation import Landmark
from tms_vision.angles import compute_joint_angles


def _lm(x, y, z=0.0, visibility=1.0):
    return Landmark(x=x, y=y, z=z, visibility=visibility)


def _base_landmarks():
    """Personne debout, de profil, tournée vers +x, posture neutre (angles ~0)."""
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


def test_neutral_posture_gives_near_zero_flexion_angles():
    landmarks = _base_landmarks()
    result = compute_joint_angles(landmarks, side="left")

    assert result is not None
    assert abs(result.trunk_flexion_deg) < 5.0
    assert abs(result.neck_flexion_deg) < 10.0


def test_trunk_flexed_forward_90_degrees_is_detected():
    landmarks = _base_landmarks()
    # Le buste bascule à l'horizontale (flexion à 90°) : les épaules
    # s'éloignent horizontalement des hanches au lieu d'être au-dessus.
    landmarks["LEFT_SHOULDER"] = _lm(0.80, 0.55)
    landmarks["RIGHT_SHOULDER"] = _lm(0.80, 0.55)
    result = compute_joint_angles(landmarks, side="left")

    assert result is not None
    assert 80.0 <= result.trunk_flexion_deg <= 100.0


def test_elbow_fully_extended_gives_near_zero_lower_arm_flexion():
    landmarks = _base_landmarks()
    # Épaule, coude et poignet alignés verticalement -> bras tendu, donc
    # flexion depuis le bras tendu (0°=tendu) proche de 0°.
    landmarks["LEFT_ELBOW"] = _lm(0.50, 0.45)
    landmarks["LEFT_WRIST"] = _lm(0.50, 0.60)
    result = compute_joint_angles(landmarks, side="left")

    assert result is not None
    assert result.lower_arm_angle_deg < 10.0


def test_missing_required_landmark_returns_none():
    landmarks = _base_landmarks()
    del landmarks["LEFT_WRIST"]
    result = compute_joint_angles(landmarks, side="left")

    assert result is None


def _profile_view_landmarks_with_degenerate_lateral_pairs():
    """Vue quasi de profil pure : épaules et oreilles se confondent presque
    en x (séparation ~0.001, largement sous MIN_LATERAL_SEPARATION_RATIO *
    torso_length ~ 0.0375 ici). Sans garde géométrique, neck_twisted,
    upper_arm_abducted et lower_arm_across_midline calculeraient tous un
    faux positif (vérifié à la main contre les formules pré-Fix-3 : les
    trois valent True), car leurs dénominateurs/références (ear_distance,
    shoulder_width) sont du bruit de mesure à cette quasi-coïncidence."""
    return {
        "LEFT_SHOULDER": _lm(0.5000, 0.30),
        "RIGHT_SHOULDER": _lm(0.5010, 0.30),
        "LEFT_HIP": _lm(0.50, 0.55),
        "RIGHT_HIP": _lm(0.50, 0.55),
        "NOSE": _lm(0.55, 0.20),
        "LEFT_EAR": _lm(0.5050, 0.22),
        "RIGHT_EAR": _lm(0.5060, 0.22),
        "LEFT_ELBOW": _lm(0.60, 0.45),
        "LEFT_WRIST": _lm(0.55, 0.60),
        "LEFT_INDEX": _lm(0.55, 0.63),
    }


def test_profile_view_degenerate_lateral_pairs_suppress_noisy_flags():
    landmarks = _profile_view_landmarks_with_degenerate_lateral_pairs()
    result = compute_joint_angles(landmarks, side="left")

    assert result is not None
    assert result.neck_twisted is False
    assert result.upper_arm_abducted is False
    assert result.lower_arm_across_midline is False


def test_front_facing_upright_with_mirrored_shoulder_order_is_not_side_bending():
    # Sujet debout de face, droit : LEFT_SHOULDER.x > RIGHT_SHOULDER.x (ordre
    # inversé par rapport aux fixtures de profil ci-dessus). Sans repliement
    # d'angle, _line_angle_from_horizontal(LEFT, RIGHT) donne ~180°, et
    # abs(180) > 10 déclencherait à tort trunk_side_bending malgré une
    # posture droite.
    landmarks = _base_landmarks()
    landmarks["LEFT_SHOULDER"] = _lm(0.55, 0.30)
    landmarks["RIGHT_SHOULDER"] = _lm(0.45, 0.30)
    landmarks["LEFT_HIP"] = _lm(0.50, 0.55)
    landmarks["RIGHT_HIP"] = _lm(0.50, 0.55)
    result = compute_joint_angles(landmarks, side="left")

    assert result is not None
    assert result.trunk_side_bending is False
