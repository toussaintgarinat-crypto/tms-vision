import cv2
import numpy as np
import pytest

from tms_vision.pipeline import analyze_video, generate_run_id, AnalysisResult, _RunningMean
from tms_vision.capture import Frame
from tms_vision.pose_estimation import Landmark, PoseEstimator, PoseResult
from tms_vision.pose3d_export import build_pose3d_payload


def test_generate_run_id_has_timestamp_and_hex_suffix():
    run_id = generate_run_id()
    date_part, time_part, hex_part = run_id.split("-")
    assert len(date_part) == 8
    assert len(time_part) == 6
    assert len(hex_part) == 6
    int(hex_part, 16)  # ne lève pas si c'est bien de l'hexadécimal


def test_running_mean_starts_at_none():
    mean = _RunningMean()
    assert mean.value is None


def test_running_mean_computes_average_incrementally():
    mean = _RunningMean()
    mean.update(2.0)
    assert mean.value == 2.0
    mean.update(4.0)
    assert mean.value == 3.0
    mean.update(9.0)
    assert mean.value == 5.0


class _EmptyFrameSource:
    def __init__(self, *_args, **_kwargs):
        pass

    def fps(self):
        return 30.0

    def __iter__(self):
        return iter([])

    def release(self):
        pass


def test_analyze_video_with_zero_frames_returns_empty_result(monkeypatch, capsys):
    monkeypatch.setattr("tms_vision.pipeline.FrameSource", _EmptyFrameSource)

    result = analyze_video(source="webcam", side="right", load_kg=0.0, wrist_twist="normal")

    assert result == AnalysisResult(empty=True)
    captured = capsys.readouterr()
    assert "Aucune frame capturée" in captured.err


def _write_synthetic_video(path):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (64, 64))
    for _ in range(3):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()


def test_analyze_video_end_to_end_on_a_blank_synthetic_video(tmp_path):
    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    result = analyze_video(source=str(video_path), side="right", load_kg=0.0, wrist_twist="normal")

    assert result.empty is False
    assert isinstance(result.video_bytes, bytes)
    assert len(result.video_bytes) > 0
    assert len(result.frame_rows) == 3
    assert result.summary["frame_count"] == 3
    assert len(result.pose3d_records) == 3


def test_analyze_video_writes_browser_playable_h264_not_mp4v(tmp_path):
    """Régression pour 9d6a9da : le fourcc d'écriture doit être "avc1" (H.264,
    lisible par les navigateurs), pas "mp4v". Écrit result.video_bytes dans un
    fichier temporaire pour le relire via cv2.VideoCapture, puisque
    analyze_video() ne renvoie plus de chemin de fichier."""
    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    result = analyze_video(source=str(video_path), side="right", load_kg=0.0, wrist_twist="normal")

    assert result.empty is False
    readback_path = tmp_path / "readback.mp4"
    readback_path.write_bytes(result.video_bytes)
    cap = cv2.VideoCapture(str(readback_path))
    try:
        fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
        fourcc = fourcc_int.to_bytes(4, byteorder="little").decode("ascii", errors="replace")
    finally:
        cap.release()

    assert fourcc == "h264", (
        f"Codec vidéo attendu 'h264' (lisible en navigateur), obtenu {fourcc!r} -- "
        "vérifier que analyze_video encode toujours avec "
        "cv2.VideoWriter_fourcc(*'avc1') et non 'mp4v'"
    )


class _InterruptingFrameSource:
    def __init__(self, *_args, **_kwargs):
        self.released = False

    def fps(self):
        return 30.0

    def __iter__(self):
        for i in range(2):
            yield Frame(
                index=i, timestamp_seconds=i / 30.0,
                image=np.zeros((64, 64, 3), dtype=np.uint8),
            )
        raise KeyboardInterrupt

    def release(self):
        self.released = True


def test_analyze_video_with_keyboard_interrupt_during_capture_still_returns_partial_result(
    monkeypatch, capsys
):
    monkeypatch.setattr("tms_vision.pipeline.FrameSource", _InterruptingFrameSource)

    result = analyze_video(source="webcam", side="right", load_kg=0.0, wrist_twist="normal")

    captured = capsys.readouterr()
    assert "Capture interrompue" in captured.out
    assert result.empty is False
    assert len(result.frame_rows) == 2


def test_analyze_video_produces_pose3d_records(tmp_path):
    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    result = analyze_video(source=str(video_path), side="right", load_kg=0.0, wrist_twist="normal")

    payload = build_pose3d_payload(result.pose3d_records)
    assert len(payload) == 3
    for entry in payload:
        assert entry["detected"] is False
        assert entry["landmarks"] is None
        assert entry["action_level"] is None
        assert entry["segment_action_levels"] is None


def _lm(x, y, z=0.0, visibility=1.0):
    return Landmark(x=x, y=y, z=z, visibility=visibility)


def test_analyze_video_merges_segment_action_levels_into_frame_rows(tmp_path, monkeypatch):
    """Les 4 colonnes {neck,trunk,upper_arm,lower_arm}_segment_action_level de
    frame_rows doivent correspondre exactement aux segment_action_levels du
    pose3d_record de la même frame (fusion faite par analyze_video, voir
    architecture)."""

    def _neutral_landmarks_2d_right_side():
        return {
            "LEFT_SHOULDER": _lm(0.50, 0.30), "RIGHT_SHOULDER": _lm(0.50, 0.30),
            "LEFT_HIP": _lm(0.50, 0.55), "RIGHT_HIP": _lm(0.50, 0.55),
            "NOSE": _lm(0.52, 0.20), "RIGHT_EAR": _lm(0.51, 0.22),
            "RIGHT_ELBOW": _lm(0.50, 0.45), "RIGHT_WRIST": _lm(0.50, 0.60),
            "RIGHT_INDEX": _lm(0.50, 0.63),
        }

    def _world_landmarks():
        return {
            "LEFT_SHOULDER": _lm(-0.1, -0.3, 0.0), "RIGHT_SHOULDER": _lm(0.1, -0.3, 0.0),
            "LEFT_HIP": _lm(-0.1, 0.0, 0.0), "RIGHT_HIP": _lm(0.1, 0.0, 0.0),
            "NOSE": _lm(0.0, -0.5, 0.05), "RIGHT_EAR": _lm(0.05, -0.48, 0.02),
            "RIGHT_ELBOW": _lm(0.15, -0.1, 0.0), "RIGHT_WRIST": _lm(0.15, 0.15, 0.0),
        }

    fake_result = PoseResult(
        landmarks=_neutral_landmarks_2d_right_side(), world_landmarks=_world_landmarks(),
    )
    monkeypatch.setattr(PoseEstimator, "process", lambda self, image_bgr: fake_result)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    result = analyze_video(source=str(video_path), side="right", load_kg=0.0, wrist_twist="normal")

    pose3d_payload = build_pose3d_payload(result.pose3d_records)
    for row, pose3d_entry in zip(result.frame_rows, pose3d_payload):
        segments = pose3d_entry["segment_action_levels"]
        assert row["neck_segment_action_level"] == segments["neck"]
        assert row["trunk_segment_action_level"] == segments["trunk"]
        assert row["upper_arm_segment_action_level"] == segments["upper_arm"]
        assert row["lower_arm_segment_action_level"] == segments["lower_arm"]


def test_analyze_video_raises_on_missing_file():
    with pytest.raises(FileNotFoundError):
        analyze_video(source="does-not-exist.mp4", side="right", load_kg=0.0, wrist_twist="normal")
