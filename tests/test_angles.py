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


def test_elbow_fully_extended_gives_180_degree_lower_arm_angle():
    landmarks = _base_landmarks()
    # Épaule, coude et poignet alignés verticalement -> bras tendu (180°).
    landmarks["LEFT_ELBOW"] = _lm(0.50, 0.45)
    landmarks["LEFT_WRIST"] = _lm(0.50, 0.60)
    result = compute_joint_angles(landmarks, side="left")

    assert result is not None
    assert result.lower_arm_angle_deg > 170.0


def test_missing_required_landmark_returns_none():
    landmarks = _base_landmarks()
    del landmarks["LEFT_WRIST"]
    result = compute_joint_angles(landmarks, side="left")

    assert result is None
