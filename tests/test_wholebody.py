import importlib.util

import numpy as np
import pytest

from tms_vision.landmark import Landmark
from tms_vision.pipeline import analyze_video
from tms_vision.pose_estimation import PoseResult
from tms_vision.pose_models import (
    FramePose, Keypoint, ModelUnavailableError, PoseModelError, PoseOptions, available_models,
    group_of,
)
from tms_vision.pose_models import rtmpose_wholebody as wb
from tests.test_hand_metrics import hand_keypoints
from tests.test_pipeline import _write_synthetic_video


def test_keypoint_layout_is_coco_wholebody():
    names = wb.KEYPOINT_NAMES
    assert len(names) == 133 and len(set(names)) == 133
    assert names[5] == "left_shoulder" and names[16] == "right_ankle"
    assert names[19] == "left_heel" and names[23] == "face_0"
    assert names[91] == "left_hand_wrist" and names[112] == "right_hand_wrist"
    assert names[91 + 8] == "left_index_tip" and names[132] == "right_pinky_tip"
    groups = [group_of(n) for n in names]
    assert groups.count("hands") == 42 and groups.count("feet") == 6 and groups.count("face") == 68 + 5


def test_raw_scores_are_converted_to_unit_confidence():
    assert wb.score_to_confidence(0.7) == 0.0 and wb.score_to_confidence(2.0) < wb.BODY_MIN_SCORE
    assert wb.score_to_confidence(7.5) == 1.0
    assert wb.BODY_MIN_SCORE < wb.score_to_confidence(3.5) < 1.0


def _person(score_body=5.0, score_other=5.0):
    points = np.tile(np.array([[100.0, 50.0]]), (133, 1)) + np.arange(133)[:, None] * [0.1, 0.2]
    scores = np.full(133, score_other)
    scores[:17] = score_body
    return points, scores


def test_person_keypoints_are_normalized_and_filtered_by_group():
    points, scores = _person()
    pose = wb._person_keypoints(points, scores, 200, 100, {"hands"}, 3)
    assert pose.frame == 3 and pose.model == "rtmpose_wholebody_133"
    assert len(pose.keypoints) == 17 + 42
    assert {k.group for k in pose.keypoints} <= {"body", "face", "hands"}  # nez/yeux/oreilles : « visage »
    shoulder = pose.by_name()["left_shoulder"]
    assert abs(shoulder.x - points[5][0] / 200) < 1e-9 and abs(shoulder.y - points[5][1] / 100) < 1e-9
    everything = wb._person_keypoints(points, scores, 200, 100, {"hands", "feet", "face"}, 0)
    assert len(everything.keypoints) == 133


def test_low_confidence_points_are_dropped_not_errors():
    points, scores = _person(score_other=0.9)  # hors champ : mains, pieds, visage
    pose = wb._person_keypoints(points, scores, 200, 100, {"hands", "feet", "face"}, 0)
    assert len(pose.keypoints) == 17


def test_choose_person_takes_largest_reliable_body():
    small, s1 = _person()
    big, s2 = _person()
    big[:17] *= 3
    junk, s3 = _person(score_body=1.0)
    junk[:17] *= 10
    assert wb.choose_person(np.stack([small, big, junk]), np.stack([s1, s2, s3])) == 1
    assert wb.choose_person(np.stack([junk]), np.stack([s3])) is None


def test_bridge_to_mediapipe_landmarks_maps_index_heel_and_toe_and_skips_weak_points():
    pose = FramePose(frame=0, model=wb.MODEL_ID, keypoints=[
        Keypoint("left_shoulder", 0.4, 0.3, confidence=0.9),
        Keypoint("right_index_mcp", 0.6, 0.6, confidence=0.8),
        Keypoint("right_big_toe", 0.6, 0.95, confidence=0.8),
        Keypoint("right_heel", 0.55, 0.96, confidence=0.8),
        Keypoint("left_elbow", 0.4, 0.5, confidence=0.1),  # trop faible : absent
        Keypoint("right_pinky_tip", 0.6, 0.6, confidence=0.9),  # sans équivalent Pose : ignoré
    ])
    landmarks = wb.to_pose_landmarks(pose)
    assert set(landmarks) == {"LEFT_SHOULDER", "RIGHT_INDEX", "RIGHT_FOOT_INDEX", "RIGHT_HEEL"}


def test_missing_install_is_reported_with_the_fix(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "rtmlib", None)
    with pytest.raises(ModelUnavailableError, match="pas installé"):
        wb.RTMPoseWholeBodyModel().load()


def _installed(monkeypatch, rtmlib: bool, weights: bool = True):
    """Simule les paquets du whole-body présents ou non, et les poids téléchargés ou non (sans
    dépendre de ce que la machine de test a en cache)."""
    monkeypatch.setattr("tms_vision.pose_models.wholebody_setup.weights_ready", lambda mode=None: weights)
    real = importlib.util.find_spec
    monkeypatch.setattr(
        "tms_vision.pose_models.registry.importlib.util.find_spec",
        lambda name, *a: (None if name in ("rtmlib", "onnxruntime") and not rtmlib
                          else object() if name in ("rtmlib", "onnxruntime") else real(name, *a)),
    )


def test_wholebody_flag_and_model_id_are_the_same_choice(monkeypatch):
    _installed(monkeypatch, True)
    a = PoseOptions(enable_wholebody=True).validate()
    b = PoseOptions(pose_model="rtmpose_wholebody_133").validate()
    assert a == b and a.enable_wholebody and a.pose_model == "rtmpose_wholebody_133"


def test_wholebody_not_installed_is_refused_with_explanation(monkeypatch):
    _installed(monkeypatch, False)
    with pytest.raises(ModelUnavailableError, match="pas installé"):
        PoseOptions(enable_wholebody=True).validate()
    assert {m["id"]: m["installed"] for m in available_models()}["rtmpose_wholebody_133"] is False


def test_wholebody_without_downloaded_weights_asks_to_prepare_the_model(monkeypatch):
    _installed(monkeypatch, True, weights=False)
    with pytest.raises(ModelUnavailableError, match="Préparer le modèle"):
        PoseOptions(enable_wholebody=True).validate()
    # sans whole-body, l'absence de poids ne concerne pas l'analyse
    assert PoseOptions(enable_hands=True).validate().enable_hands


def test_feet_and_face_are_accepted_with_wholebody_and_counted(monkeypatch):
    _installed(monkeypatch, True)
    options = PoseOptions(enable_wholebody=True, enable_hands=True, enable_feet=True).validate()
    assert options.keypoint_count == 17 + 42 + 6
    assert PoseOptions(enable_wholebody=True, enable_face=True).validate().keypoint_count == 17 + 68
    assert PoseOptions(enable_wholebody=True).validate().keypoint_count == 17


def test_hands_model_cannot_be_chosen_alone(monkeypatch):
    with pytest.raises(PoseModelError, match="complémentaire"):
        PoseOptions(pose_model="mediapipe_hands_21").validate()


def test_tiny_hands_are_not_measured():
    big = hand_keypoints("right", 90)
    assert __import__("tms_vision.hand_metrics", fromlist=["x"]).finger_curl_from_keypoints(big, "right") is not None
    tiny = [Keypoint(k.name, 0.5 + (k.x - 0.5) * 0.02, 0.5 + (k.y - 0.5) * 0.02) for k in big]
    from tms_vision.hand_metrics import finger_curl_from_keypoints
    assert finger_curl_from_keypoints(tiny, "right") is None
    assert finger_curl_from_keypoints(tiny, "right", min_span=0) is not None


def test_pipeline_with_wholebody_uses_adapter_and_returns_extra_points(tmp_path, monkeypatch):
    _installed(monkeypatch, True)
    landmarks = {
        "LEFT_SHOULDER": Landmark(0.45, 0.30, 0.0, 1.0), "RIGHT_SHOULDER": Landmark(0.55, 0.30, 0.0, 1.0),
        "LEFT_HIP": Landmark(0.45, 0.60, 0.0, 1.0), "RIGHT_HIP": Landmark(0.55, 0.60, 0.0, 1.0),
        "NOSE": Landmark(0.55, 0.20, 0.0, 1.0), "RIGHT_EAR": Landmark(0.52, 0.21, 0.0, 1.0),
        "RIGHT_ELBOW": Landmark(0.56, 0.45, 0.0, 1.0), "RIGHT_WRIST": Landmark(0.56, 0.60, 0.0, 1.0),
        "RIGHT_INDEX": Landmark(0.66, 0.66, 0.0, 1.0),
    }
    extra = FramePose(frame=0, model=wb.MODEL_ID, keypoints=hand_keypoints("right", 90)
                      + [Keypoint("right_heel", 0.55, 0.96, confidence=0.9)])

    class FakeWholeBody:
        def __init__(self, hands, feet, face):
            self.args = (hands, feet, face)
            self.last_pose = None
        def process(self, image):
            self.last_pose = extra
            return PoseResult(landmarks=landmarks, world_landmarks=None)  # 2D : pas de points monde
        def close(self): pass

    monkeypatch.setattr(wb, "WholeBodyPoseEstimator", FakeWholeBody)
    video = tmp_path / "v.mp4"
    _write_synthetic_video(video)
    result = analyze_video(str(video), "right", 0.0, "normal", anonymize=False,
                           pose_options=PoseOptions(enable_wholebody=True, enable_hands=True, enable_feet=True))
    assert result.pose_options.pose_model == "rtmpose_wholebody_133"
    assert result.keypoint_count == 65
    assert result.summary["detected_frame_count"] == 3  # RULA calculé à partir des points RTMPose
    assert result.frame_rows[0]["ankle_flexion_deg"] is None  # 2D : cheville non mesurée, pas d'erreur
    assert result.frame_rows[0]["finger_curl_deg"] > 80
    assert len(result.keypoint_frames) == 3 and result.hands_metrics["right"]["grasp_count"] == 1
