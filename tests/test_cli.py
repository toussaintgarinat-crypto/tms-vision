import numpy as np
import cv2
import pytest

from tms_vision.cli import parse_args, run, main, _RunningMean
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


def test_parse_args_defaults():
    args = parse_args(["--source", "webcam"])
    assert args.source == "webcam"
    assert args.side == "right"
    assert args.load_kg == 0.0
    assert args.wrist_twist == "normal"
    assert args.output_dir == "outputs"


def test_parse_args_rejects_negative_load():
    with pytest.raises(SystemExit):
        parse_args(["--source", "webcam", "--load-kg", "-5"])


def test_parse_args_rejects_invalid_side():
    with pytest.raises(SystemExit):
        parse_args(["--source", "webcam", "--side", "up"])


def test_parse_args_rejects_invalid_wrist_twist():
    with pytest.raises(SystemExit):
        parse_args(["--source", "webcam", "--wrist-twist", "sideways"])


class _EmptyFrameSource:
    """Simule une source vidéo qui s'ouvre correctement (contrairement à un
    vrai fichier .mp4 vide, qui échoue déjà à isOpened()) mais ne produit
    aucune frame -- le cas que le garde-fou de Fix 7c doit intercepter avant
    toute tentative d'ouverture d'un cv2.VideoWriter en taille (0, 0)."""

    def __init__(self, *_args, **_kwargs):
        pass

    def fps(self):
        return 30.0

    def __iter__(self):
        return iter([])

    def release(self):
        pass


def test_run_with_zero_frames_prints_message_and_returns_without_writing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("tms_vision.cli.FrameSource", _EmptyFrameSource)

    output_dir = tmp_path / "outputs"
    args = parse_args(["--source", "webcam", "--output-dir", str(output_dir)])
    run(args)

    captured = capsys.readouterr()
    assert "Aucune frame capturée" in captured.err
    assert list(output_dir.glob("*_annotated.mp4")) == []
    assert list(output_dir.glob("*_frames.csv")) == []
    assert list(output_dir.glob("*_summary.json")) == []


def test_run_end_to_end_on_a_blank_synthetic_video(tmp_path):
    video_path = tmp_path / "synthetic.mp4"
    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (64, 64)
    )
    for _ in range(3):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()

    output_dir = tmp_path / "outputs"
    args = parse_args(["--source", str(video_path), "--output-dir", str(output_dir)])
    run(args)

    csv_files = list(output_dir.glob("*_frames.csv"))
    summary_files = list(output_dir.glob("*_summary.json"))
    video_files = list(output_dir.glob("*_annotated.mp4"))
    assert len(csv_files) == 1
    assert len(summary_files) == 1
    assert len(video_files) == 1


def test_main_catches_keyboard_interrupt_during_processing_loop_and_exits_cleanly(
    tmp_path, monkeypatch, capsys
):
    # Fix I4 (2e revue finale) : un second Ctrl+C survenant APRÈS la capture
    # (donc pendant la boucle pose/score/écriture vidéo, hors du try/except
    # du Fix 6) ne doit plus produire de traceback brute. On simule ce
    # second Ctrl+C en interrompant draw_overlay, qui est appelé une fois
    # par frame dans cette boucle de traitement -- un seam de test propre
    # équivalent à FrameSource pour la boucle de capture.
    video_path = tmp_path / "synthetic.mp4"
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (64, 64))
    for _ in range(3):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()

    def _raise_keyboard_interrupt(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("tms_vision.cli.draw_overlay", _raise_keyboard_interrupt)

    output_dir = tmp_path / "outputs"
    monkeypatch.setattr(
        "sys.argv",
        ["tms-vision", "--source", str(video_path), "--output-dir", str(output_dir)],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Traitement interrompu par l'utilisateur." in captured.err


class _InterruptingFrameSource:
    """Simule une source vidéo qui produit quelques frames puis reçoit un
    Ctrl+C (KeyboardInterrupt) pendant la boucle de capture -- le cas que le
    Fix 6 (revue finale précédente) est censé intercepter en traitant les
    frames déjà capturées au lieu de laisser planter tout le run (Fix I3,
    2e revue finale : cette couverture de test manquait)."""

    def __init__(self, *_args, **_kwargs):
        self.released = False

    def fps(self):
        return 30.0

    def __iter__(self):
        for i in range(2):
            yield Frame(
                index=i,
                timestamp_seconds=i / 30.0,
                image=np.zeros((64, 64, 3), dtype=np.uint8),
            )
        raise KeyboardInterrupt

    def release(self):
        self.released = True


def test_run_with_keyboard_interrupt_during_capture_still_writes_partial_outputs(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr("tms_vision.cli.FrameSource", _InterruptingFrameSource)

    output_dir = tmp_path / "outputs"
    args = parse_args(["--source", "webcam", "--output-dir", str(output_dir)])
    run(args)  # ne doit PAS lever : le KeyboardInterrupt est intercepté (Fix 6)

    captured = capsys.readouterr()
    assert "Capture interrompue" in captured.out

    csv_files = list(output_dir.glob("*_frames.csv"))
    summary_files = list(output_dir.glob("*_summary.json"))
    video_files = list(output_dir.glob("*_annotated.mp4"))
    assert len(csv_files) == 1
    assert len(summary_files) == 1
    assert len(video_files) == 1
