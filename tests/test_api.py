import cv2
import numpy as np
from fastapi.testclient import TestClient

from tms_vision.api import app


def _write_synthetic_video(path):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (64, 64))
    for _ in range(3):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()


def test_create_analysis_with_no_detectable_person_returns_empty_summary(tmp_path, monkeypatch):
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    client = TestClient(app)
    with open(video_path, "rb") as video_file:
        response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["detected_frame_count"] == 0
    assert body["summary"]["max_score"] == 0
    assert body["annotated_video_url"].startswith("/outputs/")
    assert body["csv_url"].startswith("/outputs/")


def test_create_analysis_rejects_invalid_side(tmp_path, monkeypatch):
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    client = TestClient(app)
    with open(video_path, "rb") as video_file:
        response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={"side": "up", "load_kg": "0", "wrist_twist": "normal"},
        )

    assert response.status_code == 422


def test_create_analysis_rejects_unreadable_video(tmp_path, monkeypatch):
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    garbage_path = tmp_path / "not_a_video.mp4"
    garbage_path.write_bytes(b"this is not a real video file")

    client = TestClient(app)
    with open(garbage_path, "rb") as video_file:
        response = client.post(
            "/analyses",
            files={"file": ("not_a_video.mp4", video_file, "video/mp4")},
            data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
        )

    assert response.status_code == 422
