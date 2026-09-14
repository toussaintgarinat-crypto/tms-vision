import pytest
from tms_vision.cli import parse_args


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


import numpy as np
import cv2

from tms_vision.cli import parse_args, run


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
