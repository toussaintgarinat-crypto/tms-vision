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

    # --- Cou ---
    head_vec = ear - shoulder_mid
    neck_magnitude = _angle_between(head_vec, vertical)
    forward_component = (ear[0] - shoulder_mid[0]) * facing
    neck_flexion_deg = neck_magnitude if forward_component >= 0 else -neck_magnitude

    left_ear = _xy(landmarks["LEFT_EAR"]) if "LEFT_EAR" in landmarks else ear
    right_ear = _xy(landmarks["RIGHT_EAR"]) if "RIGHT_EAR" in landmarks else ear
    ear_line_angle = _line_angle_from_horizontal(left_ear, right_ear)
    shoulder_line_angle = _line_angle_from_horizontal(
        _xy(landmarks["LEFT_SHOULDER"]), _xy(landmarks["RIGHT_SHOULDER"])
    )
    neck_side_bending = abs(ear_line_angle - shoulder_line_angle) > SIDE_BEND_THRESHOLD_DEG
    ear_mid_x = (left_ear[0] + right_ear[0]) / 2.0
    ear_distance = abs(left_ear[0] - right_ear[0]) or 1e-6
    neck_twisted = abs(nose[0] - ear_mid_x) / ear_distance > 0.15

    # --- Tronc ---
    torso_vec = shoulder_mid - hip_mid
    trunk_flexion_deg = _angle_between(torso_vec, vertical)
    trunk_side_bending = abs(shoulder_line_angle) > SIDE_BEND_THRESHOLD_DEG

    # --- Bras (épaule -> coude) ---
    upper_arm_vec = elbow - side_shoulder
    upper_arm_magnitude = _angle_between(upper_arm_vec, vertical)
    upper_arm_forward = (elbow[0] - side_shoulder[0]) * facing
    upper_arm_flexion_deg = upper_arm_magnitude if upper_arm_forward >= 0 else -upper_arm_magnitude

    shoulder_width = float(
        np.linalg.norm(_xy(landmarks["LEFT_SHOULDER"]) - _xy(landmarks["RIGHT_SHOULDER"]))
    ) or 1e-6
    upper_arm_abducted = abs(elbow[0] - hip_mid[0]) > ABDUCTION_WIDTH_RATIO * shoulder_width

    baseline_y = shoulder_baseline_y if shoulder_baseline_y is not None else side_shoulder[1]
    upper_arm_shoulder_raised = (baseline_y - side_shoulder[1]) > SHOULDER_RAISE_RATIO * torso_length

    # --- Avant-bras (coude) ---
    forearm_vec = wrist - elbow
    upper_arm_from_elbow = side_shoulder - elbow
    lower_arm_angle_deg = _angle_between(upper_arm_from_elbow, forearm_vec)
    lower_arm_across_midline = abs(wrist[0] - shoulder_mid[0]) > MIDLINE_MARGIN_RATIO * torso_length and (
        (wrist[0] - shoulder_mid[0]) * (side_shoulder[0] - shoulder_mid[0]) < 0
    )

    # --- Poignet ---
    hand_vec = index_finger - wrist
    wrist_flexion_deg = 180.0 - _angle_between(forearm_vec, hand_vec)

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
