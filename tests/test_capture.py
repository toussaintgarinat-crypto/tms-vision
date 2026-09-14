import pytest
from tms_vision.capture import FrameSource

import numpy as np
import cv2


def test_missing_file_raises_file_not_found():
    with pytest.raises(FileNotFoundError):
        FrameSource("samples/does_not_exist.mp4")


def test_reads_frames_from_a_real_video_file(tmp_path):
    video_path = tmp_path / "synthetic.mp4"
    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (32, 32)
    )
    for _ in range(5):
        writer.write(np.zeros((32, 32, 3), dtype=np.uint8))
    writer.release()

    source = FrameSource(str(video_path))
    frames = list(source)
    source.release()

    assert len(frames) == 5
    assert frames[0].index == 0
    assert frames[4].index == 4
    assert frames[0].image.shape == (32, 32, 3)
