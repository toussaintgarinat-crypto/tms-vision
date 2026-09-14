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


def _neutral_profile_landmarks_with_asymmetric_subpixel_jitter():
    """Vue de profil neutre (voir _base_landmarks), mais avec un bruit
    sub-pixel réaliste (±0.008 environ, cohérent avec l'ordre de grandeur
    mesuré par le relecteur) injecté de façon ASYMÉTRIQUE sur les landmarks
    du côté droit (RIGHT_SHOULDER, RIGHT_EAR) tandis que le côté gauche reste
    à sa position de base. En vue de profil, LEFT_SHOULDER et RIGHT_SHOULDER
    (resp. LEFT_EAR/RIGHT_EAR) sont quasiment coïncidents en x : le moindre
    bruit sub-pixel asymétrique fait exploser arctan2(dy, dx) en un angle de
    ligne arbitraire (ici ~76° pour les épaules, ~-69° pour les oreilles),
    largement au-dessus de SIDE_BEND_THRESHOLD_DEG, alors que la posture
    réelle est parfaitement droite. Sans le garde-fou de séparation latérale
    (Fix C1, 2e revue finale), trunk_side_bending et neck_side_bending
    valent tous deux True ici ; avec le garde-fou, la faible séparation
    latérale (shoulder_width / ear_distance << 0.15 * torso_length) fait
    retomber les deux à False."""
    landmarks = _base_landmarks()
    landmarks["RIGHT_SHOULDER"] = _lm(0.5010, 0.3040)
    landmarks["RIGHT_EAR"] = _lm(0.5115, 0.2160)
    return landmarks


def test_neutral_profile_with_subpixel_jitter_suppresses_side_bending_flags():
    landmarks = _neutral_profile_landmarks_with_asymmetric_subpixel_jitter()
    result = compute_joint_angles(landmarks, side="left")

    assert result is not None
    assert result.trunk_side_bending is False
    assert result.neck_side_bending is False


def _profile_body_head_turned_toward_camera_landmarks():
    """Corps de profil (épaules x-dégénérées, ~0.0005 d'écart, avec un léger
    bruit vertical réaliste sur RIGHT_SHOULDER) mais tête TOURNÉE vers la
    caméra : les oreilles sont, elles, réellement séparées en x (0.535 vs
    0.475, même y -> ligne des oreilles parfaitement horizontale, angle 0°).
    Scénario exact du relecteur (3e revue finale, item 1) : neck_twisted
    doit rester détectable (oreilles séparées, nez décentré), mais
    neck_side_bending doit rester False car la moitié "épaule" de la
    comparaison (shoulder_line_angle) n'a aucun signal fiable ici — avant
    le fix, neck_side_bending n'était gardé que par ears_laterally_separated
    et laissait passer le bruit d'angle des épaules (mesuré à 89.3% de faux
    positifs par le relecteur sur un cou droit dans ce scénario)."""
    return {
        "LEFT_SHOULDER": _lm(0.5000, 0.30),
        "RIGHT_SHOULDER": _lm(0.5005, 0.304),
        "LEFT_HIP": _lm(0.50, 0.55),
        "RIGHT_HIP": _lm(0.50, 0.55),
        "NOSE": _lm(0.55, 0.20),
        "LEFT_EAR": _lm(0.535, 0.22),
        "RIGHT_EAR": _lm(0.475, 0.22),
        "LEFT_ELBOW": _lm(0.50, 0.45),
        "LEFT_WRIST": _lm(0.50, 0.60),
        "LEFT_INDEX": _lm(0.50, 0.63),
    }


def test_profile_body_with_head_turned_toward_camera_does_not_false_positive_neck_side_bending():
    landmarks = _profile_body_head_turned_toward_camera_landmarks()
    result = compute_joint_angles(landmarks, side="left")

    assert result is not None
    # Les oreilles SONT séparées et le nez EST décentré -> la torsion du cou
    # doit toujours être détectée correctement.
    assert result.neck_twisted is True
    # Mais les épaules ne sont PAS séparées de façon fiable en x -> la
    # moitié "épaule" de la comparaison ear_line_angle/shoulder_line_angle
    # est du bruit, donc pas d'inclinaison latérale du cou détectée, même
    # si les oreilles seules auraient suffi à l'ancien garde-fou.
    assert result.neck_side_bending is False


def _profile_shoulders_with_pure_vertical_discrepancy_landmarks():
    """Épaules x-dégénérées (~0.0005 d'écart, sous MIN_LATERAL_SEPARATION_RATIO
    * torso_length) mais avec un écart VERTICAL (y) entre elles assez grand
    (0.05) pour que l'ANCIEN garde-fou basé sur la norme 2D
    (shoulder_width = ||LEFT_SHOULDER - RIGHT_SHOULDER||) les considère à
    tort comme "séparées latéralement" (norme ~0.050, au-dessus du seuil
    ~0.0338 pour ce fixture), alors que arctan2(dy, dx) sur cette paire est
    quasiment ±90° de bruit (dx quasi nul) et non un vrai signal
    d'inclinaison. C'est exactement le scénario "épaule lointaine occultée,
    bruit d'estimation vertical" du relecteur (3e revue finale, item 2)."""
    return {
        "LEFT_SHOULDER": _lm(0.5000, 0.30),
        "RIGHT_SHOULDER": _lm(0.5005, 0.35),
        "LEFT_HIP": _lm(0.50, 0.55),
        "RIGHT_HIP": _lm(0.50, 0.55),
        "NOSE": _lm(0.52, 0.20),
        "LEFT_EAR": _lm(0.51, 0.22),
        "RIGHT_EAR": _lm(0.51, 0.22),
        "LEFT_ELBOW": _lm(0.50, 0.45),
        "LEFT_WRIST": _lm(0.50, 0.60),
        "LEFT_INDEX": _lm(0.50, 0.63),
    }


def test_pure_vertical_shoulder_discrepancy_does_not_false_positive_trunk_side_bending():
    landmarks = _profile_shoulders_with_pure_vertical_discrepancy_landmarks()
    result = compute_joint_angles(landmarks, side="left")

    assert result is not None
    # L'écart x réel entre les deux épaules (~0.0005) est bien en dessous du
    # seuil : le garde-fou x-only doit rejeter ce cas, même si la norme 2D
    # (gonflée par le bruit vertical à 0.05) aurait franchi le seuil sous
    # l'ancienne logique.
    assert result.trunk_side_bending is False


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
