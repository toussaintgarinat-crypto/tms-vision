import numpy as np
import cv2
import pytest

from tms_vision.pipeline import analyze_video, AnalysisResult, _RunningMean
from tms_vision.capture import Frame


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
    """Simule une source vidéo qui s'ouvre correctement mais ne produit aucune
    frame -- le cas que le garde-fou "aucune frame capturée" doit intercepter
    avant toute tentative d'ouverture d'un cv2.VideoWriter en taille (0, 0)."""

    def __init__(self, *_args, **_kwargs):
        pass

    def fps(self):
        return 30.0

    def __iter__(self):
        return iter([])

    def release(self):
        pass


def test_analyze_video_with_zero_frames_returns_empty_result_without_writing(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr("tms_vision.pipeline.FrameSource", _EmptyFrameSource)

    output_dir = tmp_path / "outputs"
    result = analyze_video(
        source="webcam", side="right", load_kg=0.0, wrist_twist="normal",
        output_dir=str(output_dir),
    )

    assert result == AnalysisResult(empty=True)
    captured = capsys.readouterr()
    assert "Aucune frame capturée" in captured.err
    assert list(output_dir.glob("*_annotated.mp4")) == []
    assert list(output_dir.glob("*_frames.csv")) == []
    assert list(output_dir.glob("*_summary.json")) == []


def test_analyze_video_end_to_end_on_a_blank_synthetic_video(tmp_path):
    video_path = tmp_path / "synthetic.mp4"
    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (64, 64)
    )
    for _ in range(3):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()

    output_dir = tmp_path / "outputs"
    result = analyze_video(
        source=str(video_path), side="right", load_kg=0.0, wrist_twist="normal",
        output_dir=str(output_dir),
    )

    assert result.empty is False
    assert result.video_path.exists()
    assert result.csv_path.exists()
    assert result.summary_json_path.exists()


def test_analyze_video_writes_browser_playable_h264_not_mp4v(tmp_path):
    """Régression pour 9d6a9da : le fourcc d'écriture doit être "avc1"
    (H.264, lisible par les navigateurs), pas "mp4v" (MPEG-4 Part 2, que
    Chromium/Firefox refusent de décoder). On vérifie via une relecture
    cv2.VideoCapture plutôt que via ffprobe (binaire externe non déclaré
    comme dépendance du projet). Sur ce build OpenCV/FFmpeg, CAP_PROP_FOURCC
    relit "h264" pour un fichier écrit avec le tag "avc1", et "FMP4" pour un
    fichier écrit avec "mp4v" -- vérifié empiriquement (y compris en
    ré-exécutant analyze_video) avant d'écrire cette assertion, donc "h264"
    est bien la valeur à verrouiller ici plutôt qu'un "avc1" deviné."""
    video_path = tmp_path / "synthetic.mp4"
    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (64, 64)
    )
    for _ in range(3):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()

    output_dir = tmp_path / "outputs"
    result = analyze_video(
        source=str(video_path), side="right", load_kg=0.0, wrist_twist="normal",
        output_dir=str(output_dir),
    )

    assert result.empty is False
    cap = cv2.VideoCapture(str(result.video_path))
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
    """Simule une source vidéo qui produit quelques frames puis reçoit un
    Ctrl+C (KeyboardInterrupt) pendant la boucle de capture."""

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


def test_analyze_video_with_keyboard_interrupt_during_capture_still_writes_partial_outputs(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr("tms_vision.pipeline.FrameSource", _InterruptingFrameSource)

    output_dir = tmp_path / "outputs"
    result = analyze_video(
        source="webcam", side="right", load_kg=0.0, wrist_twist="normal",
        output_dir=str(output_dir),
    )

    captured = capsys.readouterr()
    assert "Capture interrompue" in captured.out
    assert result.empty is False
    assert result.video_path.exists()
    assert result.csv_path.exists()
    assert result.summary_json_path.exists()


def test_analyze_video_raises_on_missing_file():
    with pytest.raises(FileNotFoundError):
        analyze_video(
            source="does-not-exist.mp4", side="right", load_kg=0.0,
            wrist_twist="normal", output_dir="outputs",
        )
