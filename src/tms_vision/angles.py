"""Calcul des angles articulaires RULA à partir des landmarks MediaPipe Pose.

Convention : coordonnées image 2D (x, y), y croît vers le bas. La capture est
supposée filmée de profil (voir README, section "Conseils de prise de vue"),
ce qui permet de donner un signe (flexion/extension) aux angles du cou et du
bras. Le tronc utilise uniquement une magnitude (RULA ne distingue pas
d'extension du tronc dans sa table).
"""
from dataclasses import dataclass

import numpy as np

from tms_vision.pose_estimation import Landmark

SIDE_BEND_THRESHOLD_DEG = 10.0
ABDUCTION_WIDTH_RATIO = 1.3
SHOULDER_RAISE_RATIO = 0.05
MIDLINE_MARGIN_RATIO = 0.05
# Séparation latérale minimale (fraction de torso_length) en dessous de
# laquelle une paire de landmarks gauche/droite est jugée trop proche de la
# vue de profil pure pour que le test qui en dépend soit fiable (division
# par une quasi-zéro, ou test de signe sur un écart bruité). 0.15 a été
# choisi empiriquement : en vue de profil stricte, ear_distance/shoulder_width
# tombent sous ~5-8% de torso_length, tandis qu'une vue à 3/4 franche reste
# au-dessus de 20-25% ; 0.15 offre une marge de part et d'autre sans couper
# les captures légèrement de profil qui restent exploitables.
MIN_LATERAL_SEPARATION_RATIO = 0.15


@dataclass
class JointAngles:
    neck_flexion_deg: float
    neck_twisted: bool
    neck_side_bending: bool
    trunk_flexion_deg: float
    trunk_twisted: bool
    trunk_side_bending: bool
    upper_arm_flexion_deg: float
    upper_arm_abducted: bool
    upper_arm_shoulder_raised: bool
    lower_arm_angle_deg: float
    lower_arm_across_midline: bool
    wrist_flexion_deg: float
    wrist_bent_from_midline: bool
    arm_supported: bool
    # Tranche 5 : mesurés hors RULA (voir extremities.py) ; None quand non visibles.
    ankle_flexion_deg: float | None = None
    finger_curl_deg: float | None = None


def _xy(landmark: Landmark) -> np.ndarray:
    return np.array([landmark.x, landmark.y])


def _midpoint(a: Landmark, b: Landmark) -> np.ndarray:
    return (_xy(a) + _xy(b)) / 2.0


def _angle_between(v1: np.ndarray, v2: np.ndarray) -> float:
    norm_product = np.linalg.norm(v1) * np.linalg.norm(v2)
    if norm_product == 0:
        return 0.0
    cosine = np.clip(np.dot(v1, v2) / norm_product, -1.0, 1.0)
    return float(np.degrees(np.arccos(cosine)))


def _line_angle_from_horizontal(a: np.ndarray, b: np.ndarray) -> float:
    delta = b - a
    return float(np.degrees(np.arctan2(delta[1], delta[0])))


def _fold_to_half_range(angle_deg: float) -> float:
    """Replie un angle de ligne (co-domaine (-180, 180] de arctan2) dans
    (-90, 90]. Une ligne définie par deux points n'a pas de "sens" propre
    (gauche->droite ou droite->gauche donnent des angles opposés à 180°
    près) : ce repliement rend le test d'inclinaison insensible à l'ordre
    des points passés à _line_angle_from_horizontal."""
    if angle_deg > 90.0:
        return angle_deg - 180.0
    if angle_deg <= -90.0:
        return angle_deg + 180.0
    return angle_deg


def compute_ankle_flexion(world_landmarks: dict[str, Landmark], side: str) -> float | None:
    """Écart de la cheville à la position neutre (jambe et pied à angle droit), en degrés.
    Positif : pointe du pied vers le bas (flexion plantaire) ; négatif : pointe relevée
    (flexion dorsale). `None` si genou, cheville, talon ou pointe du pied ne sont pas visibles.

    Contrairement aux autres angles de ce module, il se calcule en 3D sur les points « monde » de
    MediaPipe (en mètres) : un angle de cheville en image 2D dépend trop de l'angle de prise de
    vue (mesuré sur une vraie vidéo : environ 58° constants en 2D contre environ 10° en 3D pour un
    pied à plat). L'axe du pied est talon -> orteils."""
    prefix = side.upper()
    names = [f"{prefix}_KNEE", f"{prefix}_ANKLE", f"{prefix}_HEEL", f"{prefix}_FOOT_INDEX"]
    if any(name not in world_landmarks for name in names):
        return None
    knee, ankle, heel, toes = (
        np.array([world_landmarks[n].x, world_landmarks[n].y, world_landmarks[n].z]) for n in names
    )
    # Angle entre la jambe (cheville -> genou) et le pied : 90° au neutre, plus grand = pointe tendue.
    return _angle_between(knee - ankle, toes - heel) - 90.0


REQUIRED_COMMON = ["LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_HIP", "RIGHT_HIP", "NOSE"]
REQUIRED_PER_SIDE = ["SHOULDER", "ELBOW", "WRIST", "EAR", "INDEX"]


def compute_joint_angles(
    landmarks: dict[str, Landmark], side: str, shoulder_baseline_y: float | None = None
) -> JointAngles | None:
    side_prefix = side.upper()
    required = list(REQUIRED_COMMON) + [f"{side_prefix}_{name}" for name in REQUIRED_PER_SIDE]
    if any(name not in landmarks for name in required):
        return None

    shoulder_mid = _midpoint(landmarks["LEFT_SHOULDER"], landmarks["RIGHT_SHOULDER"])
    hip_mid = _midpoint(landmarks["LEFT_HIP"], landmarks["RIGHT_HIP"])
    torso_length = float(np.linalg.norm(shoulder_mid - hip_mid)) or 1e-6

    nose = _xy(landmarks["NOSE"])
    facing = 1.0 if nose[0] >= shoulder_mid[0] else -1.0

    side_shoulder = _xy(landmarks[f"{side_prefix}_SHOULDER"])
    elbow = _xy(landmarks[f"{side_prefix}_ELBOW"])
    wrist = _xy(landmarks[f"{side_prefix}_WRIST"])
    ear = _xy(landmarks[f"{side_prefix}_EAR"])
    index_finger = _xy(landmarks[f"{side_prefix}_INDEX"])

    vertical = np.array([0.0, -1.0])

    # Séparations latérales gauche/droite calculées en amont des sections
    # Cou/Tronc/Bras ci-dessous, car chacune d'elles s'en sert pour décider
    # si son test d'inclinaison/torsion est géométriquement fiable (voir
    # Fix C1 de la 2e revue finale, puis Fix générique de la 3e revue finale).
    #
    # shoulder_width est la norme 2D (LEFT_SHOULDER, RIGHT_SHOULDER) : c'est
    # une échelle de largeur d'épaules légitime pour upper_arm_abducted
    # (ABDUCTION_WIDTH_RATIO * shoulder_width) et DOIT rester une norme pour
    # cet usage — un écart purement vertical n'élargit pas réellement la
    # carrure, mais c'est une échelle de repère à l'image, pas une mesure de
    # fiabilité géométrique comme shoulder_x_separation ci-dessous.
    #
    # shoulder_x_separation / shoulders_laterally_separated, en revanche,
    # servent à décider si arctan2(dy, dx) sur CETTE paire de landmarks (via
    # shoulder_line_angle) est fiable. arctan2 dépend de dx, pas de la norme :
    # un écart purement vertical entre les deux épaules (dx quasi nul, dy
    # grand) fait passer la norme au-dessus du seuil alors que dx reste du
    # bruit sub-pixel, ce qui laissait shoulder_line_angle proche de ±90° de
    # bruit filer sans garde-fou (Fix 3e revue finale, item 2). Le garde-fou
    # doit donc être calculé sur l'écart en x SEUL, pas sur la norme.
    shoulder_width = float(
        np.linalg.norm(_xy(landmarks["LEFT_SHOULDER"]) - _xy(landmarks["RIGHT_SHOULDER"]))
    )
    shoulder_x_separation = abs(
        landmarks["LEFT_SHOULDER"].x - landmarks["RIGHT_SHOULDER"].x
    )
    shoulders_laterally_separated = (
        shoulder_x_separation >= MIN_LATERAL_SEPARATION_RATIO * torso_length
    )

    # --- Cou ---
    head_vec = ear - shoulder_mid
    neck_magnitude = _angle_between(head_vec, vertical)
    forward_component = (ear[0] - shoulder_mid[0]) * facing
    neck_flexion_deg = neck_magnitude if forward_component >= 0 else -neck_magnitude

    left_ear = _xy(landmarks["LEFT_EAR"]) if "LEFT_EAR" in landmarks else ear
    right_ear = _xy(landmarks["RIGHT_EAR"]) if "RIGHT_EAR" in landmarks else ear
    ear_mid_x = (left_ear[0] + right_ear[0]) / 2.0
    ear_distance = abs(left_ear[0] - right_ear[0])
    ears_laterally_separated = ear_distance >= MIN_LATERAL_SEPARATION_RATIO * torso_length

    # Repliement dans (-90, 90] : une ligne gauche->droite et sa réciproque
    # droite->gauche ne doivent pas être vues comme des inclinaisons opposées.
    ear_line_angle = _fold_to_half_range(_line_angle_from_horizontal(left_ear, right_ear))
    shoulder_line_angle = _fold_to_half_range(
        _line_angle_from_horizontal(
            _xy(landmarks["LEFT_SHOULDER"]), _xy(landmarks["RIGHT_SHOULDER"])
        )
    )
    # neck_side_bending compare DEUX angles de ligne indépendants
    # (ear_line_angle ET shoulder_line_angle) : il n'est fiable que si LES
    # DEUX paires de landmarks sous-jacentes sont assez séparées en x. Gater
    # uniquement sur ears_laterally_separated (comme avant la 3e revue
    # finale) laisse passer un shoulder_line_angle de bruit quand la tête est
    # tournée vers la caméra (oreilles séparées) mais le corps reste de
    # profil (épaules x-dégénérées) — le relecteur a mesuré 89.3% de faux
    # positifs sur un cou droit dans exactement ce scénario.
    if ears_laterally_separated and shoulders_laterally_separated:
        neck_side_bending = bool(abs(ear_line_angle - shoulder_line_angle) > SIDE_BEND_THRESHOLD_DEG)
    else:
        # L'une des deux paires (oreilles ou épaules) se confond en x : au
        # moins un des deux angles de ligne comparés est un repliement de
        # bruit sub-pixel -> arctan2(dy, dx) n'a plus de signal fiable pour
        # au moins un des deux termes de la comparaison. Pas d'inclinaison
        # détectée.
        neck_side_bending = False

    if ears_laterally_separated:
        neck_twisted = bool(abs(nose[0] - ear_mid_x) / ear_distance > 0.15)
    else:
        # Vue quasi de profil : les deux oreilles se confondent en x, le
        # ratio (nose_x - ear_mid_x) / ear_distance explose et devient du
        # bruit. Pas de signal fiable -> pas de torsion détectée.
        neck_twisted = False

    # --- Tronc ---
    torso_vec = shoulder_mid - hip_mid
    trunk_flexion_deg = _angle_between(torso_vec, vertical)
    if shoulders_laterally_separated:
        trunk_side_bending = bool(abs(shoulder_line_angle) > SIDE_BEND_THRESHOLD_DEG)
    else:
        # shoulders_laterally_separated est maintenant un écart x SEUL (Fix
        # 3e revue finale, item 2) : les deux épaules se confondent en x,
        # shoulder_line_angle devient un repliement de bruit sub-pixel ->
        # arctan2(dy, dx) n'a plus de signal fiable, MEME si un écart
        # vertical (y) entre les deux épaules aurait fait paraître la norme
        # shoulder_width suffisamment grande. Pas d'inclinaison détectée.
        trunk_side_bending = False

    # --- Bras (épaule -> coude) ---
    # RULA : neutre (0°) = bras pendant le long du corps, càd upper_arm_vec
    # (épaule -> coude, qui pointe vers le BAS pour un bras pendant) aligné
    # avec le bas de l'image, PAS avec le "haut" utilisé par cou/tronc.
    downward = np.array([0.0, 1.0])
    upper_arm_vec = elbow - side_shoulder
    upper_arm_magnitude = _angle_between(upper_arm_vec, downward)
    upper_arm_forward = (elbow[0] - side_shoulder[0]) * facing
    upper_arm_flexion_deg = upper_arm_magnitude if upper_arm_forward >= 0 else -upper_arm_magnitude

    if shoulders_laterally_separated:
        upper_arm_abducted = bool(abs(elbow[0] - hip_mid[0]) > ABDUCTION_WIDTH_RATIO * shoulder_width)
    else:
        # Vue quasi de profil (écart x des épaules sous le seuil) : la
        # carrure réelle du sujet vue de face est trop réduite à l'image
        # pour que shoulder_width (norme, gardée telle quelle pour cet
        # usage — voir Fix 3e revue finale, item 1) serve de référence de
        # largeur fiable pour juger une abduction.
        upper_arm_abducted = False

    baseline_y = shoulder_baseline_y if shoulder_baseline_y is not None else side_shoulder[1]
    upper_arm_shoulder_raised = bool(
        (baseline_y - side_shoulder[1]) > SHOULDER_RAISE_RATIO * torso_length
    )

    # --- Avant-bras (coude) ---
    # Convention "flexion depuis le bras tendu" (0°=tendu, 90°=coude à angle
    # droit), cohérente avec les autres angles (0°=neutre). L'angle interne
    # brut (180°=tendu) est converti via 180° - angle_interne.
    forearm_vec = wrist - elbow
    upper_arm_from_elbow = side_shoulder - elbow
    lower_arm_angle_deg = 180.0 - _angle_between(upper_arm_from_elbow, forearm_vec)
    if shoulders_laterally_separated:
        lower_arm_across_midline = bool(
            abs(wrist[0] - shoulder_mid[0]) > MIDLINE_MARGIN_RATIO * torso_length
            and (wrist[0] - shoulder_mid[0]) * (side_shoulder[0] - shoulder_mid[0]) < 0
        )
    else:
        # side_shoulder.x et shoulder_mid.x se confondent en profil : le
        # test de signe (wrist.x - shoulder_mid.x) * (side_shoulder.x -
        # shoulder_mid.x) n'a plus de sens géométrique.
        lower_arm_across_midline = False

    # --- Poignet ---
    # forearm_vec (coude -> poignet) et hand_vec (poignet -> index) sont
    # parallèles pour un poignet droit -> _angle_between renvoie déjà ~0°
    # (neutre) sans transformation supplémentaire.
    hand_vec = index_finger - wrist
    wrist_flexion_deg = _angle_between(forearm_vec, hand_vec)

    return JointAngles(
        neck_flexion_deg=neck_flexion_deg,
        neck_twisted=neck_twisted,
        neck_side_bending=neck_side_bending,
        trunk_flexion_deg=trunk_flexion_deg,
        trunk_twisted=False,  # rotation axiale du tronc = phénomène en profondeur (z), non fiable en capture 2D de profil (limite PoC)
        trunk_side_bending=trunk_side_bending,
        upper_arm_flexion_deg=upper_arm_flexion_deg,
        upper_arm_abducted=upper_arm_abducted,
        upper_arm_shoulder_raised=upper_arm_shoulder_raised,
        lower_arm_angle_deg=lower_arm_angle_deg,
        lower_arm_across_midline=lower_arm_across_midline,
        wrist_flexion_deg=wrist_flexion_deg,
        wrist_bent_from_midline=False,  # non détectable de façon fiable en monoculaire (limite PoC)
        arm_supported=False,  # non détectable sans segmentation de surface (limite PoC)
    )
