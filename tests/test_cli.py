import numpy as np
import cv2
import pytest

from tms_vision.cli import parse_args, run, main


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


def test_run_prints_output_paths_on_success(tmp_path, capsys):
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

    captured = capsys.readouterr()
    assert "Vidéo annotée :" in captured.out
    assert "Export CSV/JSON :" in captured.out


def test_main_catches_keyboard_interrupt_during_processing_loop_and_exits_cleanly(
    tmp_path, monkeypatch, capsys
):
    # Un second Ctrl+C survenant APRÈS la capture (donc pendant la boucle
    # pose/score/écriture vidéo) ne doit pas produire de traceback brute. On
    # simule ce second Ctrl+C en interrompant draw_overlay, appelé une fois
    # par frame dans cette boucle -- désormais dans pipeline.py.
    video_path = tmp_path / "synthetic.mp4"
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (64, 64))
    for _ in range(3):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()

    def _raise_keyboard_interrupt(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("tms_vision.pipeline.draw_overlay", _raise_keyboard_interrupt)

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
