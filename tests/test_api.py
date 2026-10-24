import tempfile
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from tms_vision import storage
from tms_vision.api import app
from tms_vision.exercises import REGIONS


def _write_synthetic_video(path):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (64, 64))
    for _ in range(3):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()


def _patch_db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.duckdb")


def test_create_analysis_with_no_detectable_person_returns_empty_summary(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
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
    assert body["annotated_video_url"] == f"/analyses/{body['analysis_id']}/video"
    assert body["csv_url"] == f"/analyses/{body['analysis_id']}/frames.csv"
    assert body["pose3d_url"] == f"/analyses/{body['analysis_id']}/pose3d"
    assert body["side"] == "right"


def test_create_analysis_accepts_worker_and_poste_label(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    client = TestClient(app)
    with open(video_path, "rb") as video_file:
        response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={
                "side": "right", "load_kg": "0", "wrist_twist": "normal",
                "worker_label": "Marie D.", "poste_label": "Poste emballage",
            },
        )

    assert response.status_code == 200
    analysis_id = response.json()["analysis_id"]
    stored = storage.get_analysis(analysis_id)
    assert stored["worker_label"] == "Marie D."
    assert stored["poste_label"] == "Poste emballage"


def test_create_analysis_rejects_negative_load_kg(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    client = TestClient(app)
    with open(video_path, "rb") as video_file:
        response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={"side": "right", "load_kg": "-1", "wrist_twist": "normal"},
        )

    assert response.status_code == 422


def test_create_analysis_rejects_invalid_side(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
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
    _patch_db(tmp_path, monkeypatch)
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


def test_analysis_resources_are_actually_served_at_returned_urls(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
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

    video_response = client.get(body["annotated_video_url"])
    assert video_response.status_code == 200
    assert len(video_response.content) > 0
    assert "attachment" in video_response.headers.get("content-disposition", "")

    csv_response = client.get(body["csv_url"])
    assert csv_response.status_code == 200
    assert len(csv_response.content) > 0
    assert "attachment" in csv_response.headers.get("content-disposition", "")

    pose3d_response = client.get(body["pose3d_url"])
    assert pose3d_response.status_code == 200
    assert len(pose3d_response.content) > 0


def test_get_analysis_video_without_range_header_returns_full_content(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    client = TestClient(app)
    with open(video_path, "rb") as video_file:
        create_response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
        )
    body = create_response.json()
    full_video_bytes = storage.get_video_bytes(body["analysis_id"])

    response = client.get(body["annotated_video_url"])

    assert response.status_code == 200
    assert response.content == full_video_bytes
    assert response.headers["accept-ranges"] == "bytes"
    assert "attachment" in response.headers.get("content-disposition", "")


def test_get_analysis_video_with_valid_range_returns_206_partial_content(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    client = TestClient(app)
    with open(video_path, "rb") as video_file:
        create_response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
        )
    body = create_response.json()
    full_video_bytes = storage.get_video_bytes(body["analysis_id"])
    total_length = len(full_video_bytes)
    end = min(9, total_length - 1)

    response = client.get(body["annotated_video_url"], headers={"Range": f"bytes=0-{end}"})

    assert response.status_code == 206
    assert response.content == full_video_bytes[: end + 1]
    assert response.headers["content-range"] == f"bytes 0-{end}/{total_length}"
    assert response.headers["content-length"] == str(end + 1)
    assert response.headers["accept-ranges"] == "bytes"


def test_get_analysis_video_with_out_of_bounds_range_returns_416(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    client = TestClient(app)
    with open(video_path, "rb") as video_file:
        create_response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
        )
    body = create_response.json()
    total_length = len(storage.get_video_bytes(body["analysis_id"]))

    response = client.get(
        body["annotated_video_url"],
        headers={"Range": f"bytes={total_length + 1000}-{total_length + 2000}"},
    )

    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{total_length}"


def test_get_analysis_video_returns_404_for_unknown_id(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    assert client.get("/analyses/does-not-exist/video").status_code == 404
    assert client.get("/analyses/does-not-exist/pose3d").status_code == 404
    assert client.get("/analyses/does-not-exist/frames.csv").status_code == 404
    assert client.get("/analyses/does-not-exist").status_code == 404


def test_list_analyses_returns_created_analysis(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    client = TestClient(app)
    with open(video_path, "rb") as video_file:
        create_response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
        )
    analysis_id = create_response.json()["analysis_id"]

    list_response = client.get("/analyses")

    assert list_response.status_code == 200
    ids = [item["id"] for item in list_response.json()]
    assert analysis_id in ids


def test_list_analyses_worker_label_query_param_narrows_http_response(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    client = TestClient(app)

    def _create(worker_label):
        with open(video_path, "rb") as video_file:
            response = client.post(
                "/analyses",
                files={"file": ("synthetic.mp4", video_file, "video/mp4")},
                data={
                    "side": "right", "load_kg": "0", "wrist_twist": "normal",
                    "worker_label": worker_label,
                },
            )
        return response.json()["analysis_id"]

    marie_id = _create("Marie D.")
    paul_id = _create("Paul L.")

    response = client.get("/analyses", params={"worker_label": "Marie D."})

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()]
    assert ids == [marie_id]
    assert paul_id not in ids


def test_create_analysis_cleans_up_temp_file_when_upload_copy_fails(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    created_paths = []
    original_named_temporary_file = tempfile.NamedTemporaryFile

    def _tracking_named_temporary_file(*args, **kwargs):
        handle = original_named_temporary_file(*args, **kwargs)
        created_paths.append(Path(handle.name))
        return handle

    monkeypatch.setattr(
        "tms_vision.api.tempfile.NamedTemporaryFile", _tracking_named_temporary_file
    )

    def _raise_copyfileobj(*_args, **_kwargs):
        raise OSError("disque plein simulé")

    monkeypatch.setattr("tms_vision.api.shutil.copyfileobj", _raise_copyfileobj)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    client = TestClient(app, raise_server_exceptions=False)
    with open(video_path, "rb") as video_file:
        response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
        )

    assert response.status_code == 500
    assert len(created_paths) == 1
    assert not created_paths[0].exists()


def test_start_upload_creates_session_with_metadata(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    response = client.post("/uploads", data={"filename": "clip.mp4", "total_chunks": "3"})

    assert response.status_code == 200
    upload_id = response.json()["upload_id"]
    meta_path = tmp_path / ".uploads" / upload_id / "meta.json"
    assert meta_path.is_file()


def test_start_upload_rejects_zero_total_chunks(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    response = client.post("/uploads", data={"filename": "clip.mp4", "total_chunks": "0"})

    assert response.status_code == 422


def test_upload_chunk_writes_chunk_file(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    start_response = client.post("/uploads", data={"filename": "clip.mp4", "total_chunks": "2"})
    upload_id = start_response.json()["upload_id"]

    response = client.put(
        f"/uploads/{upload_id}/chunks/0",
        files={"file": ("chunk-0", b"hello", "application/octet-stream")},
    )

    assert response.status_code == 200
    chunk_path = tmp_path / ".uploads" / upload_id / "chunk_000000"
    assert chunk_path.read_bytes() == b"hello"


def test_upload_chunk_rejects_unknown_upload_id(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    response = client.put(
        "/uploads/does-not-exist/chunks/0",
        files={"file": ("chunk-0", b"hello", "application/octet-stream")},
    )

    assert response.status_code == 404


def test_upload_chunk_rejects_out_of_range_index(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    start_response = client.post("/uploads", data={"filename": "clip.mp4", "total_chunks": "2"})
    upload_id = start_response.json()["upload_id"]

    response = client.put(
        f"/uploads/{upload_id}/chunks/5",
        files={"file": ("chunk-5", b"hello", "application/octet-stream")},
    )

    assert response.status_code == 400


def test_upload_chunks_then_complete_matches_direct_analysis(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)
    video_bytes = video_path.read_bytes()
    midpoint = len(video_bytes) // 2
    chunks = [video_bytes[:midpoint], video_bytes[midpoint:]]

    client = TestClient(app)
    start_response = client.post(
        "/uploads", data={"filename": "synthetic.mp4", "total_chunks": str(len(chunks))}
    )
    upload_id = start_response.json()["upload_id"]

    for index, chunk in enumerate(chunks):
        chunk_response = client.put(
            f"/uploads/{upload_id}/chunks/{index}",
            files={"file": (f"chunk-{index}", chunk, "application/octet-stream")},
        )
        assert chunk_response.status_code == 200

    response = client.post(
        f"/uploads/{upload_id}/complete",
        data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["annotated_video_url"] == f"/analyses/{body['analysis_id']}/video"
    assert body["side"] == "right"
    assert not (tmp_path / ".uploads" / upload_id).exists()

    with open(video_path, "rb") as video_file:
        direct_response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
        )
    assert direct_response.status_code == 200
    assert body["summary"] == direct_response.json()["summary"]


def test_chunks_reassembled_by_index_regardless_of_arrival_order(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)
    video_bytes = video_path.read_bytes()
    midpoint = len(video_bytes) // 2
    chunks = [video_bytes[:midpoint], video_bytes[midpoint:]]

    client = TestClient(app)
    start_response = client.post("/uploads", data={"filename": "synthetic.mp4", "total_chunks": "2"})
    upload_id = start_response.json()["upload_id"]

    client.put(
        f"/uploads/{upload_id}/chunks/1",
        files={"file": ("chunk-1", chunks[1], "application/octet-stream")},
    )
    client.put(
        f"/uploads/{upload_id}/chunks/0",
        files={"file": ("chunk-0", chunks[0], "application/octet-stream")},
    )

    response = client.post(
        f"/uploads/{upload_id}/complete",
        data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
    )

    assert response.status_code == 200
    assert response.json()["summary"]["frame_count"] == 3


def test_complete_upload_fails_when_chunk_missing(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    start_response = client.post("/uploads", data={"filename": "clip.mp4", "total_chunks": "2"})
    upload_id = start_response.json()["upload_id"]

    client.put(
        f"/uploads/{upload_id}/chunks/0",
        files={"file": ("chunk-0", b"data", "application/octet-stream")},
    )

    response = client.post(
        f"/uploads/{upload_id}/complete",
        data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
    )

    assert response.status_code == 422


def test_complete_upload_rejects_unknown_upload_id(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    response = client.post(
        "/uploads/does-not-exist/complete",
        data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
    )

    assert response.status_code == 404


def test_create_analysis_rejects_video_estimated_too_large(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("tms_vision.api.MAX_ESTIMATED_MEMORY_BYTES", 1)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    client = TestClient(app)
    with open(video_path, "rb") as video_file:
        response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
        )

    assert response.status_code == 422


def test_complete_upload_cleans_up_session_on_analysis_failure(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    start_response = client.post("/uploads", data={"filename": "garbage.mp4", "total_chunks": "1"})
    upload_id = start_response.json()["upload_id"]

    client.put(
        f"/uploads/{upload_id}/chunks/0",
        files={"file": ("chunk-0", b"this is not a real video file", "application/octet-stream")},
    )

    response = client.post(
        f"/uploads/{upload_id}/complete",
        data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
    )

    assert response.status_code == 422
    assert not (tmp_path / ".uploads" / upload_id).exists()


def test_upload_chunk_overwrite_keeps_last_write(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    start_response = client.post("/uploads", data={"filename": "clip.mp4", "total_chunks": "1"})
    upload_id = start_response.json()["upload_id"]

    client.put(
        f"/uploads/{upload_id}/chunks/0",
        files={"file": ("chunk-0", b"first-attempt", "application/octet-stream")},
    )
    client.put(
        f"/uploads/{upload_id}/chunks/0",
        files={"file": ("chunk-0", b"second-attempt-wins", "application/octet-stream")},
    )

    chunk_path = tmp_path / ".uploads" / upload_id / "chunk_000000"
    assert chunk_path.read_bytes() == b"second-attempt-wins"


def test_start_upload_rejects_excessive_total_chunks(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    response = client.post("/uploads", data={"filename": "clip.mp4", "total_chunks": "100000"})

    assert response.status_code == 422


def test_upload_chunk_rejects_malformed_upload_id(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    response = client.put(
        "/uploads/not-a-uuid/chunks/0",
        files={"file": ("chunk-0", b"data", "application/octet-stream")},
    )

    assert response.status_code == 404


def test_get_recommendation_returns_404_for_unknown_id(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    response = client.get("/analyses/does-not-exist/recommendation")
    assert response.status_code == 404


def test_get_recommendation_returns_null_zone_when_nothing_is_degraded(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)

    client = TestClient(app)
    with open(video_path, "rb") as video_file:
        create_response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
        )
    analysis_id = create_response.json()["analysis_id"]

    # Vidéo synthétique noire : aucune pose détectée -> aucun segment_action_level
    # jamais non-null -> aucune zone ne peut être dégradée.
    response = client.get(f"/analyses/{analysis_id}/recommendation")

    assert response.status_code == 200
    body = response.json()
    assert body["zone"] is None
    assert body["capsule"] is None


def test_get_recommendation_returns_worst_zone_and_matching_capsule(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)

    summary = {
        "frame_count": 1, "detected_frame_count": 1, "max_score": 7,
        "average_score": 7.0, "time_by_action_level": {"changement_immediat": 1.0},
    }
    row = {field: None for field in storage.CSV_FIELDS}
    row.update(frame_index=0, timestamp_seconds=0.0, detected=True)
    row["neck_segment_action_level"] = "acceptable"
    row["trunk_segment_action_level"] = "changement_immediat"
    row["upper_arm_segment_action_level"] = "acceptable"
    row["lower_arm_segment_action_level"] = "acceptable"
    storage.save_analysis(
        analysis_id="rec-1", created_at=datetime.now(timezone.utc),
        side="right", load_kg=0.0, wrist_twist="normal", worker_label=None, poste_label=None,
        summary=summary, video_bytes=b"x", pose3d_json="[]", frame_rows=[row],
    )

    client = TestClient(app)
    response = client.get("/analyses/rec-1/recommendation")

    assert response.status_code == 200
    body = response.json()
    assert body["zone"] == "trunk"
    assert body["capsule"]["zone"] == "trunk"
    assert body["capsule"]["title"]
    assert body["capsule"]["description"]
    assert body["capsule"]["video_url"]


def _save_analysis_with_frames(analysis_id, frame_rows):
    summary = {
        "frame_count": len(frame_rows), "detected_frame_count": len(frame_rows),
        "max_score": 1, "average_score": 1.0, "time_by_action_level": {},
    }
    storage.save_analysis(
        analysis_id=analysis_id, created_at=datetime.now(timezone.utc),
        side="right", load_kg=0.0, wrist_twist="normal", worker_label=None, poste_label=None,
        summary=summary, video_bytes=b"x", pose3d_json="[]", frame_rows=frame_rows,
    )


def _frame_row(index, timestamp, trunk_angle=None, trunk_level="acceptable"):
    row = {field: None for field in storage.CSV_FIELDS}
    row.update(
        frame_index=index, timestamp_seconds=timestamp, detected=trunk_angle is not None,
        trunk_flexion_deg=trunk_angle,
    )
    row["neck_segment_action_level"] = "acceptable"
    row["trunk_segment_action_level"] = trunk_level
    row["upper_arm_segment_action_level"] = "acceptable"
    row["lower_arm_segment_action_level"] = "acceptable"
    return row


def _sawtooth_frames():
    # Tronc 0 / 20 degres toutes les 10 s sur 60 s : 2.5 cycles, donc 2.5 cycles/min,
    # niveau eleve sur les frames paires.
    return [
        _frame_row(
            i, i * 10.0, trunk_angle=0.0 if i % 2 == 0 else 20.0,
            trunk_level="changement_immediat" if i % 2 == 0 else "acceptable",
        )
        for i in range(7)
    ]


def test_create_bilan_uses_nine_hour_default_and_can_be_read_back(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)

    created = client.post("/bilans", json={"label": "Quai 3"})

    assert created.status_code == 200
    body = created.json()
    assert body["label"] == "Quai 3"
    assert body["workday_hours"] == 9.0
    fetched = client.get(f"/bilans/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["items"] == []
    assert [b["id"] for b in client.get("/bilans").json()] == [body["id"]]


@pytest.mark.parametrize("workday_hours", [0, -1, 25])
def test_create_bilan_rejects_invalid_workday_hours(tmp_path, monkeypatch, workday_hours):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post("/bilans", json={"workday_hours": workday_hours})

    assert response.status_code == 422


def test_get_bilan_returns_404_for_unknown_id(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)

    assert client.get("/bilans/nope").status_code == 404
    assert client.get("/bilans/nope/recurrence").status_code == 404


def test_attach_analysis_returns_updated_bilan(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    _save_analysis_with_frames("a-1", _sawtooth_frames())
    client = TestClient(app)
    bilan_id = client.post("/bilans", json={}).json()["id"]

    response = client.post(
        f"/bilans/{bilan_id}/analyses",
        json={"analysis_id": "a-1", "activity_hours": 5.0, "representative": True},
    )

    assert response.status_code == 200
    assert response.json()["items"] == [
        {"analysis_id": "a-1", "activity_hours": 5.0, "representative": True}
    ]


def test_attach_analysis_error_statuses(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    _save_analysis_with_frames("a-1", _sawtooth_frames())
    _save_analysis_with_frames("a-2", _sawtooth_frames())
    client = TestClient(app)
    bilan_id = client.post("/bilans", json={"workday_hours": 8.0}).json()["id"]
    payload = {"analysis_id": "a-1", "activity_hours": 5.0, "representative": True}

    assert client.post("/bilans/nope/analyses", json=payload).status_code == 404
    assert client.post(
        f"/bilans/{bilan_id}/analyses", json={**payload, "analysis_id": "nope"}
    ).status_code == 404
    assert client.post(
        f"/bilans/{bilan_id}/analyses", json={**payload, "activity_hours": 0}
    ).status_code == 422
    assert client.post(f"/bilans/{bilan_id}/analyses", json=payload).status_code == 200
    assert client.post(f"/bilans/{bilan_id}/analyses", json=payload).status_code == 409
    # 5 h deja documentees + 4 h > 8 h de journee.
    too_long = {"analysis_id": "a-2", "activity_hours": 4.0, "representative": True}
    assert client.post(f"/bilans/{bilan_id}/analyses", json=too_long).status_code == 422


def test_get_analysis_recurrence_returns_indicators(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    _save_analysis_with_frames("a-1", _sawtooth_frames())
    client = TestClient(app)

    response = client.get("/analyses/a-1/recurrence")

    assert response.status_code == 200
    body = response.json()
    assert body["sample_seconds"] == 60.0
    assert body["thresholds_calibrated"] is False
    trunk = body["zones"]["trunk"]
    assert trunk["cycles"] == 2.5
    assert trunk["cycles_per_minute"] == 2.5
    assert trunk["assessment"] is None


def test_get_analysis_recurrence_returns_404_for_unknown_id(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)

    assert client.get("/analyses/nope/recurrence").status_code == 404


def test_bilan_recurrence_projects_only_representative_analyses(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    _save_analysis_with_frames("a-1", _sawtooth_frames())
    _save_analysis_with_frames("a-2", _sawtooth_frames())
    client = TestClient(app)
    bilan_id = client.post("/bilans", json={"workday_hours": 9.0}).json()["id"]
    client.post(f"/bilans/{bilan_id}/analyses",
                json={"analysis_id": "a-1", "activity_hours": 5.0, "representative": True})
    client.post(f"/bilans/{bilan_id}/analyses",
                json={"analysis_id": "a-2", "activity_hours": 3.0, "representative": False})

    response = client.get(f"/bilans/{bilan_id}/recurrence")

    assert response.status_code == 200
    body = response.json()
    assert body["documented_hours"] == 8.0
    assert body["undocumented_hours"] == 1.0
    assert body["thresholds_calibrated"] is False
    # 2.5 cycles/min * 60 * 5 h ; l'analyse non representative est exclue.
    assert body["zones"]["trunk"]["projected_cycles"] == 750.0
    by_id = {a["analysis_id"]: a for a in body["analyses"]}
    assert by_id["a-1"]["included"] is True
    assert by_id["a-2"]["included"] is False
    # Niveau eleve sur 4 frames paires de 10 s chacune sauf la derniere (0 s) : 30 s / 60 s * 5 h.
    assert body["zones"]["trunk"]["projected_elevated_hours"] == pytest.approx(2.5)


def test_bilan_recurrence_of_empty_bilan(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    bilan_id = client.post("/bilans", json={}).json()["id"]

    body = client.get(f"/bilans/{bilan_id}/recurrence").json()

    assert body["undocumented_hours"] == 9.0
    assert body["analyses"] == []


def _scored_analysis(analysis_id, load_kg=0.0, muscle_use=1, posture_angles=None):
    """Analyse cohérente : lignes et résumé produits par le vrai moteur RULA au poids
    d'origine, de sorte que compute_rula_score serve d'oracle indépendant au recalcul."""
    from tms_vision.angles import JointAngles
    from tms_vision.export import FrameRecord, ResultsExporter
    from tms_vision.rula.scoring import compute_rula_score

    angles = posture_angles or JointAngles(
        neck_flexion_deg=5.0, neck_twisted=False, neck_side_bending=False,
        trunk_flexion_deg=1.0, trunk_twisted=False, trunk_side_bending=False,
        upper_arm_flexion_deg=10.0, upper_arm_abducted=False, upper_arm_shoulder_raised=False,
        lower_arm_angle_deg=90.0, lower_arm_across_midline=False,
        wrist_flexion_deg=0.5, wrist_bent_from_midline=False, arm_supported=False,
    )
    exporter = ResultsExporter()
    for index in range(3):
        score = compute_rula_score(angles, wrist_twist=1, load_kg=load_kg, muscle_use_score=muscle_use)
        exporter.add_frame(FrameRecord(index, float(index), True, angles, score))
    rows = exporter.rows()
    for row in rows:
        for zone in ("neck", "trunk", "upper_arm", "lower_arm"):
            row[f"{zone}_segment_action_level"] = "acceptable"
    storage.save_analysis(
        analysis_id=analysis_id, created_at=datetime.now(timezone.utc), side="right",
        load_kg=load_kg, wrist_twist="normal", worker_label=None, poste_label=None,
        summary=exporter.summary(), video_bytes=b"x", pose3d_json="[]", frame_rows=rows,
    )
    return angles


def _oracle_max_score(angles, load_kg, muscle_use=1):
    from tms_vision.rula.scoring import compute_rula_score

    return compute_rula_score(
        angles, wrist_twist=1, load_kg=load_kg, muscle_use_score=muscle_use
    ).final_score


def test_put_exact_load_recomputes_scores_like_the_scoring_engine(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    angles = _scored_analysis("w-1", load_kg=0.0)
    client = TestClient(app)

    response = client.put("/analyses/w-1/load", json={"kind": "exact", "kg": 15})

    assert response.status_code == 200
    body = response.json()
    assert body["max_score"] == _oracle_max_score(angles, 15.0)
    assert body["max_score"] > _oracle_max_score(angles, 0.0)
    assert body["load_kg"] == 15.0
    assert body["load"]["kind"] == "exact"
    assert body["load"]["kg"] == 15.0
    assert body["load"]["original_load_kg"] == 0.0
    assert body["load"]["score_range"] is None
    assert client.get("/analyses/w-1").json()["max_score"] == body["max_score"]


def test_put_range_straddling_a_threshold_stores_worst_case_and_the_interval(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    angles = _scored_analysis("w-1", load_kg=0.0)
    low_expected = _oracle_max_score(angles, 8.0)
    high_expected = _oracle_max_score(angles, 12.0)
    assert low_expected < high_expected  # precondition : la fourchette change vraiment le score
    client = TestClient(app)

    body = client.put(
        "/analyses/w-1/load", json={"kind": "range", "kg_min": 8, "kg_max": 12}
    ).json()

    assert body["max_score"] == high_expected
    assert body["load_kg"] == 12.0
    assert body["load"]["kind"] == "range"
    assert (body["load"]["kg_min"], body["load"]["kg_max"]) == (8.0, 12.0)
    assert body["load"]["score_range"]["low"]["max_score"] == low_expected
    assert body["load"]["score_range"]["high"]["max_score"] == high_expected


def test_put_range_within_one_threshold_band_has_equal_low_and_high_scores(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    _scored_analysis("w-1", load_kg=0.0)
    client = TestClient(app)

    body = client.put(
        "/analyses/w-1/load", json={"kind": "range", "kg_min": 3, "kg_max": 8}
    ).json()

    score_range = body["load"]["score_range"]
    assert score_range["low"]["max_score"] == score_range["high"]["max_score"]


def test_put_none_resets_to_zero_kg_and_is_idempotent(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    angles = _scored_analysis("w-1", load_kg=20.0)
    client = TestClient(app)

    first = client.put("/analyses/w-1/load", json={"kind": "none"}).json()
    second = client.put("/analyses/w-1/load", json={"kind": "none"}).json()

    assert first == second
    assert first["load_kg"] == 0.0
    assert first["load"]["kind"] == "none"
    assert first["max_score"] == _oracle_max_score(angles, 0.0)


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "range", "kg_min": 12, "kg_max": 8},
        {"kind": "exact", "kg": -1},
        {"kind": "exact"},
        {"kind": "range", "kg_min": 5},
        {"kind": "exact", "kg": 600},
        {"kind": "none", "kg": 5},
        {"kind": "unknown"},
    ],
)
def test_put_load_rejects_invalid_payloads_without_changing_anything(tmp_path, monkeypatch, payload):
    _patch_db(tmp_path, monkeypatch)
    _scored_analysis("w-1", load_kg=0.0)
    client = TestClient(app)
    before = client.get("/analyses/w-1").json()

    response = client.put("/analyses/w-1/load", json=payload)

    assert response.status_code == 422
    assert client.get("/analyses/w-1").json() == before


def test_put_load_unknown_analysis_returns_404(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)

    assert client.put("/analyses/nope/load", json={"kind": "exact", "kg": 5}).status_code == 404


def test_put_load_422_message_is_readable(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    _scored_analysis("w-1")
    client = TestClient(app)

    response = client.put("/analyses/w-1/load", json={"kind": "range", "kg_min": 12, "kg_max": 8})

    assert isinstance(response.json()["detail"], str)
    assert "borne" in response.json()["detail"]


def test_load_kg_is_optional_when_creating_an_analysis():
    schemas = app.openapi()["components"]["schemas"]
    for name, schema in schemas.items():
        if name.startswith("Body_create_analysis") or name.startswith("Body_complete_upload"):
            assert "load_kg" in schema["properties"], name
            assert "load_kg" not in schema.get("required", []), name
            assert "side" in schema["required"], name


def _segment_row(index, timestamp, **levels):
    row = {field: None for field in storage.CSV_FIELDS}
    row.update(frame_index=index, timestamp_seconds=timestamp, detected=True)
    for zone in ("neck", "trunk", "upper_arm", "lower_arm"):
        row[f"{zone}_segment_action_level"] = levels.get(zone, "acceptable")
    return row


def _save_with_segments(analysis_id, rows, load_kg=0.0):
    storage.save_analysis(
        analysis_id=analysis_id, created_at=datetime.now(timezone.utc), side="right",
        load_kg=load_kg, wrist_twist="normal", worker_label=None, poste_label=None,
        summary={"frame_count": len(rows), "detected_frame_count": len(rows), "max_score": 1,
                 "average_score": 1.0, "time_by_action_level": {}},
        video_bytes=b"x", pose3d_json="[]", frame_rows=rows,
    )


def test_recommendation_returns_a_ranked_program_and_keeps_first_zone_and_capsule(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    hot = "changement_immediat"
    _save_with_segments("p-1", [
        _segment_row(0, 0.0, trunk=hot, neck=hot, upper_arm=hot),
        _segment_row(1, 4.0, trunk=hot, neck="acceptable", upper_arm="acceptable"),
        _segment_row(2, 6.0, trunk="acceptable"),
    ])
    client = TestClient(app)

    body = client.get("/analyses/p-1/recommendation").json()

    assert [item["zone"] for item in body["program"]] == ["trunk", "neck", "upper_arm"]
    assert [item["rank"] for item in body["program"]] == [1, 2, 3]
    assert body["zone"] == "trunk"
    assert body["capsule"] == body["program"][0]["capsule"]
    assert body["capsule"]["kind"] == "stretch"
    assert body["gesture_corrections"] == []
    assert body["program"][0]["reason"].startswith("Tronc : 6 s")


def test_recommendation_with_a_single_loaded_zone_has_a_single_item(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    _save_with_segments("p-1", [_segment_row(0, 0.0, neck="changement_immediat"), _segment_row(1, 2.0)])
    client = TestClient(app)

    body = client.get("/analyses/p-1/recommendation").json()

    assert [item["zone"] for item in body["program"]] == ["neck"]
    assert body["zone"] == "neck"


def test_recommendation_without_any_risk_has_an_empty_program(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    _save_with_segments("p-1", [_segment_row(0, 0.0), _segment_row(1, 1.0)])
    client = TestClient(app)

    body = client.get("/analyses/p-1/recommendation").json()

    assert body["program"] == []
    assert body["zone"] is None
    assert body["capsule"] is None
    assert body["gesture_corrections"] == []


def test_recommendation_reason_mentions_the_entered_load_but_ranking_ignores_it(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    hot = "changement_immediat"
    _save_with_segments("p-1", [
        _segment_row(0, 0.0, neck=hot, trunk="acceptable"), _segment_row(1, 5.0),
    ])
    client = TestClient(app)
    before = client.get("/analyses/p-1/recommendation").json()
    # Le recalcul de score exige des sous-scores ; on ne passe donc pas par PUT ici mais par le
    # stockage direct, pour verifier uniquement le texte du motif.
    storage.update_load(
        "p-1", load={"kind": "range", "kg": None, "kg_min": 8.0, "kg_max": 12.0},
        effective_load_kg=12.0, frame_scores=[], score_range=None,
        summary={"max_score": 1, "average_score": 1.0, "time_by_action_level": {}},
    )

    after = client.get("/analyses/p-1/recommendation").json()

    assert [i["zone"] for i in after["program"]] == [i["zone"] for i in before["program"]]
    assert after["program"][0]["reason"].endswith("(charge manipulée : 8 à 12 kg).")
    assert "charge" not in before["program"][0]["reason"]
    assert after["load"]["kind"] == "range"


def test_recommendation_returns_404_for_unknown_analysis_still(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)

    assert TestClient(app).get("/analyses/nope/recommendation").status_code == 404


def test_bilan_program_ranks_zones_by_projected_hours(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    hot = "changement_immediat"
    # a-1 : tronc eleve 50 % du temps ; a-2 : cou eleve 100 % du temps (frames de 10 s).
    _save_with_segments("a-1", [
        _segment_row(0, 0.0, trunk=hot), _segment_row(1, 10.0), _segment_row(2, 20.0),
    ])
    _save_with_segments("a-2", [
        _segment_row(0, 0.0, neck=hot), _segment_row(1, 10.0, neck=hot), _segment_row(2, 20.0),
    ])
    client = TestClient(app)
    bilan_id = client.post("/bilans", json={"workday_hours": 9.0}).json()["id"]
    for analysis_id, hours in (("a-1", 6.0), ("a-2", 3.0)):
        client.post(f"/bilans/{bilan_id}/analyses",
                    json={"analysis_id": analysis_id, "activity_hours": hours, "representative": True})

    body = client.get(f"/bilans/{bilan_id}/program").json()

    # a-1 : 10 s sur 20 s = 50 % de 6 h = 3 h de tronc ; a-2 : 20 s sur 20 s = 100 % de 3 h = 3 h de cou.
    # Egalite a 3 h -> ordre fixe : tronc avant cou.
    assert [item["zone"] for item in body["program"]] == ["trunk", "neck"]
    assert body["program"][0]["reason"] == "Tronc : environ 3 h en posture à risque sur 9 h estimées."
    assert body["gesture_corrections"] == []
    assert body["warnings"] == []


def test_bilan_program_excludes_non_representative_analyses(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    hot = "changement_immediat"
    _save_with_segments("a-1", [_segment_row(0, 0.0, trunk=hot), _segment_row(1, 10.0), _segment_row(2, 20.0)])
    client = TestClient(app)
    bilan_id = client.post("/bilans", json={}).json()["id"]
    client.post(f"/bilans/{bilan_id}/analyses",
                json={"analysis_id": "a-1", "activity_hours": 4.0, "representative": False})

    body = client.get(f"/bilans/{bilan_id}/program").json()

    assert body["program"] == []
    assert any("représentative" in warning for warning in body["warnings"])


def test_bilan_program_of_empty_bilan_and_unknown_bilan(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    bilan_id = client.post("/bilans", json={}).json()["id"]

    assert client.get(f"/bilans/{bilan_id}/program").json()["program"] == []
    assert client.get("/bilans/nope/program").status_code == 404


def test_list_exercises_returns_the_catalog_without_the_heavy_fields(tmp_path, monkeypatch):
    client = TestClient(app)

    response = client.get("/exercises")

    assert response.status_code == 200
    body = response.json()
    assert [e["id"] for e in body] == sorted(e["id"] for e in body)
    assert {e["zone"] for e in body} == set(REGIONS)
    for exercise in body:
        assert exercise["status"] == "draft"
        assert exercise["duration_seconds"] > 0
        assert "poses" not in exercise
        assert "keyframes" not in exercise
        assert "instructions" not in exercise


def test_get_exercise_returns_the_full_definition(tmp_path, monkeypatch):
    client = TestClient(app)

    response = client.get("/exercises/neck-lateral-stretch")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "neck-lateral-stretch"
    assert body["poses"]["neutral"] == {}
    assert body["keyframes"][0] == {"t": 0, "pose": "neutral"}
    assert body["instructions"][0]["text"]


def test_get_exercise_returns_404_for_unknown_or_malicious_ids(tmp_path, monkeypatch):
    client = TestClient(app)

    assert client.get("/exercises/unknown").status_code == 404
    assert client.get("/exercises/..%2Fsecret").status_code == 404
    assert client.get("/exercises/drafts").status_code == 404


# --- Vidéos d'exercices et refactor de la réponse vidéo avec Range -----------------------

VIDEO_BYTES = bytes(range(256)) * 4  # 1024 octets reconnaissables


def _seed_capsule_video(tmp_path, monkeypatch, exercise_id="neck-lateral-stretch", content=VIDEO_BYTES):
    from tms_vision import capsule_build

    capsules_dir = tmp_path / "capsules"
    capsules_dir.mkdir(exist_ok=True)
    (capsules_dir / f"{exercise_id}.mp4").write_bytes(content)
    monkeypatch.setattr(capsule_build, "CAPSULES_DIR", capsules_dir)
    return capsules_dir


def test_capsule_video_is_served_whole(tmp_path, monkeypatch):
    _seed_capsule_video(tmp_path, monkeypatch)

    response = TestClient(app).get("/capsules/neck-lateral-stretch/video")

    assert response.status_code == 200
    assert response.content == VIDEO_BYTES
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-disposition"].startswith("inline")


def test_capsule_video_supports_range_requests(tmp_path, monkeypatch):
    _seed_capsule_video(tmp_path, monkeypatch)
    client = TestClient(app)

    partial = client.get("/capsules/neck-lateral-stretch/video", headers={"Range": "bytes=10-19"})
    suffix = client.get("/capsules/neck-lateral-stretch/video", headers={"Range": "bytes=-4"})
    unsatisfiable = client.get(
        "/capsules/neck-lateral-stretch/video", headers={"Range": "bytes=2000-3000"}
    )

    assert partial.status_code == 206
    assert partial.content == VIDEO_BYTES[10:20]
    assert partial.headers["content-range"] == f"bytes 10-19/{len(VIDEO_BYTES)}"
    assert suffix.status_code == 206
    assert suffix.content == VIDEO_BYTES[-4:]
    assert unsatisfiable.status_code == 416
    assert unsatisfiable.headers["content-range"] == f"bytes */{len(VIDEO_BYTES)}"


def test_capsule_video_is_404_when_not_generated_yet(tmp_path, monkeypatch):
    _seed_capsule_video(tmp_path, monkeypatch, exercise_id="trunk-lumbar-mobility")

    response = TestClient(app).get("/capsules/neck-lateral-stretch/video")

    assert response.status_code == 404
    assert "non générée" in response.json()["detail"]


@pytest.mark.parametrize("capsule_id", ["unknown", "..%2Fsecret", "drafts", "neck-lateral-stretch.mp4"])
def test_capsule_video_is_404_for_ids_outside_the_catalog(tmp_path, monkeypatch, capsule_id):
    capsules_dir = _seed_capsule_video(tmp_path, monkeypatch)
    # Un fichier existant sous un nom hors catalogue ne doit jamais être servi.
    (capsules_dir / "unknown.mp4").write_bytes(b"secret")
    (tmp_path / "secret.mp4").write_bytes(b"secret")

    assert TestClient(app).get(f"/capsules/{capsule_id}/video").status_code == 404


def test_analysis_video_still_supports_range_requests_after_the_refactor(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    storage.save_analysis(
        analysis_id="v-1", created_at=datetime.now(timezone.utc), side="right", load_kg=0.0,
        wrist_twist="normal", worker_label=None, poste_label=None,
        summary={"frame_count": 0, "detected_frame_count": 0, "max_score": 0,
                 "average_score": 0, "time_by_action_level": {}},
        video_bytes=VIDEO_BYTES, pose3d_json="[]", frame_rows=[],
    )
    client = TestClient(app)

    whole = client.get("/analyses/v-1/video")
    partial = client.get("/analyses/v-1/video", headers={"Range": "bytes=0-9"})
    bad = client.get("/analyses/v-1/video", headers={"Range": "bytes=9999-19999"})

    assert whole.status_code == 200 and whole.content == VIDEO_BYTES
    assert whole.headers["content-disposition"] == 'attachment; filename="v-1_annotated.mp4"'
    assert partial.status_code == 206 and partial.content == VIDEO_BYTES[:10]
    assert bad.status_code == 416
    assert client.get("/analyses/nope/video").status_code == 404


def _hot_segments_analysis(analysis_id):
    hot = "changement_immediat"
    rows = [_segment_row(0, 0.0, trunk=hot, neck=hot), _segment_row(1, 4.0)]
    _save_with_segments(analysis_id, rows)


def test_recommendation_reports_whether_each_capsule_video_exists(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    _hot_segments_analysis("p-1")
    _seed_capsule_video(tmp_path, monkeypatch, exercise_id="trunk-lumbar-mobility")
    client = TestClient(app)

    body = client.get("/analyses/p-1/recommendation").json()

    by_zone = {item["zone"]: item["capsule"] for item in body["program"]}
    assert by_zone["trunk"]["video_available"] is True
    assert by_zone["neck"]["video_available"] is False
    assert body["capsule"]["video_available"] is True  # premier élément = tronc
    assert by_zone["trunk"]["video_url"] == "/capsules/trunk-lumbar-mobility/video"
    assert by_zone["trunk"]["status"] == "draft"


def test_bilan_program_reports_whether_each_capsule_video_exists(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    hot = "changement_immediat"
    _save_with_segments("a-1", [
        _segment_row(0, 0.0, neck=hot), _segment_row(1, 10.0, neck=hot), _segment_row(2, 20.0),
    ])
    client = TestClient(app)
    bilan_id = client.post("/bilans", json={"workday_hours": 9.0}).json()["id"]
    client.post(f"/bilans/{bilan_id}/analyses",
                json={"analysis_id": "a-1", "activity_hours": 4.0, "representative": True})

    _seed_capsule_video(tmp_path, monkeypatch, exercise_id="trunk-lumbar-mobility")
    without_video = client.get(f"/bilans/{bilan_id}/program").json()["program"]
    _seed_capsule_video(tmp_path, monkeypatch, exercise_id="neck-lateral-stretch")
    with_video = client.get(f"/bilans/{bilan_id}/program").json()["program"]

    assert without_video[0]["zone"] == "neck"
    assert without_video[0]["capsule"]["video_available"] is False
    assert with_video[0]["capsule"]["video_available"] is True


def _task_payload(**overrides):
    return {"name": "Peindre un plafond", "zones": ["upper_arm"], "activity_hours": 2.0,
            "cycles_per_minute": 10.0, **overrides}


def test_task_routes_create_update_delete_and_report(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    bilan_id = client.post("/bilans", json={"workday_hours": 8.0}).json()["id"]

    created = client.post(f"/bilans/{bilan_id}/tasks", json=_task_payload())

    assert created.status_code == 200
    [task] = created.json()["tasks"]
    assert task["name"] == "Peindre un plafond"
    assert task["source"] == "practitioner"
    report = client.get(f"/bilans/{bilan_id}/recurrence").json()
    assert report["zones"]["upper_arm"]["projected_cycles"] == 10 * 60 * 2
    assert report["documented_hours"] == 2.0
    assert report["tasks"][0]["name"] == "Peindre un plafond"

    updated = client.put(f"/bilans/{bilan_id}/tasks/{task['id']}",
                         json=_task_payload(cycles_per_minute=5.0))
    assert updated.status_code == 200
    assert client.get(f"/bilans/{bilan_id}/recurrence").json()[
        "zones"]["upper_arm"]["projected_cycles"] == 5 * 60 * 2

    deleted = client.delete(f"/bilans/{bilan_id}/tasks/{task['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["tasks"] == []


def test_task_hours_are_derived_from_time_slots(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    bilan_id = client.post("/bilans", json={}).json()["id"]
    payload = _task_payload(activity_hours=None, time_slots=[
        {"start": "08:00", "end": "12:00"}, {"start": "13:00", "end": "14:30"}])

    task = client.post(f"/bilans/{bilan_id}/tasks", json=payload).json()["tasks"][0]

    assert task["activity_hours"] == 5.5


def test_task_validation_errors(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    bilan_id = client.post("/bilans", json={"workday_hours": 8.0}).json()["id"]
    url = f"/bilans/{bilan_id}/tasks"

    assert client.post("/bilans/nope/tasks", json=_task_payload()).status_code == 404
    assert client.put(f"{url}/nope", json=_task_payload()).status_code == 404
    assert client.delete(f"{url}/nope").status_code == 404

    invalid = [
        _task_payload(name="   "),
        _task_payload(zones=[]),
        _task_payload(zones=["genou"]),
        _task_payload(activity_hours=0),
        _task_payload(activity_hours=25),
        _task_payload(cycles_per_minute=-1),
        _task_payload(activity_hours=None),
        _task_payload(activity_hours=None, time_slots=[{"start": "10:00", "end": "09:00"}]),
        _task_payload(activity_hours=None, time_slots=[{"start": "8h", "end": "9h"}]),
        _task_payload(analysis_id="inconnue"),
        _task_payload(activity_hours=9.0),
    ]
    for payload in invalid:
        assert client.post(url, json=payload).status_code == 422, payload

    french = client.post(url, json=_task_payload(name=" ")).json()["detail"]
    assert french == "Le nom de la tâche est obligatoire."


def test_task_completing_a_video_overrides_its_measure(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    _save_analysis_with_frames("a-1", _sawtooth_frames())
    client = TestClient(app)
    bilan_id = client.post("/bilans", json={"workday_hours": 9.0}).json()["id"]
    client.post(f"/bilans/{bilan_id}/analyses",
                json={"analysis_id": "a-1", "activity_hours": 5.0, "representative": True})

    response = client.post(f"/bilans/{bilan_id}/tasks", json=_task_payload(
        zones=["trunk"], activity_hours=None, cycles_per_minute=8.0, analysis_id="a-1"))

    assert response.status_code == 200
    report = client.get(f"/bilans/{bilan_id}/recurrence").json()
    assert report["zones"]["trunk"]["projected_cycles"] == 8 * 60 * 5
    assert report["documented_hours"] == 5.0
    [entry] = report["analyses"]
    assert entry["declared"][0]["measured_cycles_per_minute"]["trunk"] == 2.5


def test_attaching_a_video_counts_standalone_tasks_in_the_workday(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    _save_analysis_with_frames("a-1", _sawtooth_frames())
    client = TestClient(app)
    bilan_id = client.post("/bilans", json={"workday_hours": 8.0}).json()["id"]
    client.post(f"/bilans/{bilan_id}/tasks", json=_task_payload(activity_hours=4.0))

    too_long = client.post(f"/bilans/{bilan_id}/analyses",
                           json={"analysis_id": "a-1", "activity_hours": 5.0,
                                 "representative": True})

    assert too_long.status_code == 422


def test_task_accepts_a_frequency_per_zone_and_workstation_fields(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    bilan_id = client.post("/bilans", json={"workday_hours": 8.0}).json()["id"]
    payload = _task_payload(
        zones=["neck", "lower_arm"], cycles_per_minute=None,
        zone_cycles_per_minute={"neck": 6.0, "lower_arm": 20.0},
        workstation=" Assis devant écran ", breaks="Pauses courtes toutes les 2 h",
    )

    [task] = client.post(f"/bilans/{bilan_id}/tasks", json=payload).json()["tasks"]

    assert task["zone_cycles"] == {"neck": 6.0, "lower_arm": 20.0}
    assert task["workstation"] == "Assis devant écran"
    assert task["breaks"] == "Pauses courtes toutes les 2 h"
    report = client.get(f"/bilans/{bilan_id}/recurrence").json()
    assert report["zones"]["neck"]["projected_cycles"] == 6 * 60 * 2
    assert report["zones"]["lower_arm"]["projected_cycles"] == 20 * 60 * 2
    assert report["documented_hours"] == 2.0


def test_shortcut_frequency_fills_only_zones_without_their_own_value(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    bilan_id = client.post("/bilans", json={}).json()["id"]
    payload = _task_payload(zones=["neck", "hand"], cycles_per_minute=3.0,
                            zone_cycles_per_minute={"neck": 9.0})

    [task] = client.post(f"/bilans/{bilan_id}/tasks", json=payload).json()["tasks"]

    assert task["zone_cycles"] == {"neck": 9.0, "hand": 3.0}


def test_frequency_for_an_unchecked_zone_is_rejected(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    bilan_id = client.post("/bilans", json={}).json()["id"]

    response = client.post(f"/bilans/{bilan_id}/tasks", json=_task_payload(
        zones=["neck"], zone_cycles_per_minute={"foot": 2.0}))

    assert response.status_code == 422
    assert "pas cochée" in response.json()["detail"]
    negative = client.post(f"/bilans/{bilan_id}/tasks", json=_task_payload(
        zones=["neck"], zone_cycles_per_minute={"neck": -1.0}))
    assert negative.status_code == 422


def test_bilan_program_is_seated_for_a_seated_workstation_and_says_so(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    _save_analysis_with_frames("a-1", _sawtooth_frames())
    client = TestClient(app)
    bilan_id = client.post("/bilans", json={"workday_hours": 9.0}).json()["id"]
    client.post(f"/bilans/{bilan_id}/analyses",
                json={"analysis_id": "a-1", "activity_hours": 5.0, "representative": True})

    before = client.get(f"/bilans/{bilan_id}/program").json()
    assert before["position"] is None and before["position_note"] is None
    assert before["program"][0]["capsule"]["id"] == "trunk-lumbar-mobility"

    client.post(f"/bilans/{bilan_id}/tasks",
                json=_task_payload(workstation="Assis devant écran", activity_hours=3.0))
    after = client.get(f"/bilans/{bilan_id}/program").json()

    assert after["position"] == "seated"
    assert "assis" in after["position_note"]
    assert after["program"][0]["capsule"]["id"] == "seated-round-hollow-back"


def test_duplicate_bilan_copies_the_tasks_but_not_the_videos(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    _save_analysis_with_frames("a-1", _sawtooth_frames())
    client = TestClient(app)
    original_id = client.post("/bilans", json={"label": "Quai 3", "workday_hours": 7.5}).json()["id"]
    client.post(f"/bilans/{original_id}/analyses",
                json={"analysis_id": "a-1", "activity_hours": 5.0, "representative": True})
    client.post(f"/bilans/{original_id}/tasks", json=_task_payload(name="Peindre", notes="note"))
    client.post(f"/bilans/{original_id}/tasks", json=_task_payload(
        name="Contrôler", zones=["trunk"], activity_hours=None, cycles_per_minute=8.0,
        analysis_id="a-1"))

    response = client.post(f"/bilans/{original_id}/duplicate", json={"label": "Sophie Martin"})

    assert response.status_code == 200
    copy = response.json()
    assert copy["id"] != original_id
    assert copy["label"] == "Sophie Martin"
    assert copy["workday_hours"] == 7.5
    assert copy["items"] == []
    assert [task["name"] for task in copy["tasks"]] == ["Peindre", "Contrôler"]
    assert copy["tasks"][0]["notes"] == "note"
    assert all(task["analysis_id"] is None for task in copy["tasks"])
    assert {task["id"] for task in copy["tasks"]}.isdisjoint(
        task["id"] for task in client.get(f"/bilans/{original_id}").json()["tasks"]
    )
    # L'original ne bouge pas : sa vidéo et le lien de sa fiche sont intacts.
    original = client.get(f"/bilans/{original_id}").json()
    assert [item["analysis_id"] for item in original["items"]] == ["a-1"]
    assert original["tasks"][1]["analysis_id"] == "a-1"


def test_duplicate_bilan_default_label_and_unknown_bilan(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    named = client.post("/bilans", json={"label": "Quai 3"}).json()["id"]
    unnamed = client.post("/bilans", json={}).json()["id"]

    assert client.post(f"/bilans/{named}/duplicate", json={}).json()["label"] == "Copie de Quai 3"
    assert client.post(f"/bilans/{unnamed}/duplicate", json={"label": "  "}).json()[
        "label"] == "Copie de bilan"
    assert client.post("/bilans/nope/duplicate", json={}).status_code == 404


def test_metiers_library_lists_the_shipped_models(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)

    models = client.get("/metiers").json()

    assert len(models) >= 10
    assert {model["origin"] for model in models} == {"library"}
    assert all(model["status"] == "draft" and model["tasks"] for model in models)


def test_create_bilan_from_metier_prefills_label_hours_and_tasks(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    model = next(m for m in client.get("/metiers").json() if m["id"] == "bureau-gestionnaire")

    response = client.post("/metiers/bureau-gestionnaire/bilan", json={"label": "Sophie Martin"})

    assert response.status_code == 200
    bilan = response.json()
    assert bilan["label"] == "Sophie Martin"
    assert bilan["workday_hours"] == model["workday_hours"]
    assert bilan["items"] == []
    assert [task["name"] for task in bilan["tasks"]] == [task["name"] for task in model["tasks"]]
    first = bilan["tasks"][0]
    assert first["workstation"] == "Assis devant écran"
    assert first["zone_cycles"] == {zone: 20 for zone in first["zones"]}
    assert first["source"] == "practitioner" and first["analysis_id"] is None
    # Le bilan créé se projette comme n'importe quel autre.
    assert client.get(f"/bilans/{bilan['id']}/recurrence").status_code == 200
    assert client.get(f"/bilans/{bilan['id']}/program").status_code == 200
    # Sans libellé, le titre du métier sert de nom.
    unnamed = client.post("/metiers/bureau-gestionnaire/bilan", json={}).json()
    assert unnamed["label"] == model["title"]


def test_every_library_metier_creates_a_valid_bilan(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)

    for model in client.get("/metiers").json():
        response = client.post(f"/metiers/{model['id']}/bilan", json={})
        assert response.status_code == 200, model["id"]
        assert client.get(f"/bilans/{response.json()['id']}/program").status_code == 200


def test_create_bilan_from_unknown_metier_returns_404(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)

    assert client.post("/metiers/nope/bilan", json={}).status_code == 404


def test_save_bilan_as_metier_then_reuse_and_delete_it(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    _save_analysis_with_frames("a-1", _sawtooth_frames())
    client = TestClient(app)
    bilan_id = client.post("/bilans", json={"label": "Quai 3", "workday_hours": 7.5}).json()["id"]
    client.post(f"/bilans/{bilan_id}/analyses",
                json={"analysis_id": "a-1", "activity_hours": 2.0, "representative": True})
    client.post(f"/bilans/{bilan_id}/tasks", json=_task_payload(
        name="Peindre", zones=["upper_arm", "hand"], zone_cycles_per_minute={
            "upper_arm": 10.0, "hand": 30.0}, cycles_per_minute=None, workstation="Conduite",
        notes="note", load_kg=4.0))

    saved = client.post(f"/bilans/{bilan_id}/metier", json={"title": " Peintre atelier "})

    assert saved.status_code == 200
    model = saved.json()
    assert model["origin"] == "custom" and model["id"].startswith("perso-")
    assert model["title"] == "Peintre atelier"
    assert model["workday_hours"] == 7.5
    assert model["tasks"] == [{
        "name": "Peindre", "zones": ["upper_arm", "hand"], "activity_hours": 2.0,
        "zone_cycles": {"upper_arm": 10.0, "hand": 30.0}, "load_kg": 4.0,
        "workstation": "Conduite", "notes": "note",
    }]
    assert model["id"] in [m["id"] for m in client.get("/metiers").json()]

    reused = client.post(f"/metiers/{model['id']}/bilan", json={"label": "Paul"}).json()
    assert reused["tasks"][0]["zone_cycles"] == {"upper_arm": 10.0, "hand": 30.0}
    assert reused["tasks"][0]["load_kg"] == 4.0

    assert client.delete(f"/metiers/{model['id']}").status_code == 200
    assert client.delete(f"/metiers/{model['id']}").status_code == 404
    assert model["id"] not in [m["id"] for m in client.get("/metiers").json()]


def test_save_bilan_as_metier_needs_a_task_and_library_models_stay(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    empty = client.post("/bilans", json={}).json()["id"]

    assert client.post(f"/bilans/{empty}/metier", json={"title": "X"}).status_code == 422
    assert client.post(f"/bilans/{empty}/metier", json={"title": ""}).status_code == 422
    assert client.post("/bilans/nope/metier", json={"title": "X"}).status_code == 404
    assert client.delete("/metiers/bureau-gestionnaire").status_code == 403


def test_cors_preflight_allows_delete_from_the_web_origin(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.options(
        "/bilans/x/tasks/y",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "DELETE"},
    )

    assert response.status_code == 200
    assert "DELETE" in response.headers["access-control-allow-methods"]


def test_bilan_program_without_video_is_proposed_from_the_tasks(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    bilan_id = client.post("/metiers/bureau-gestionnaire/bilan", json={}).json()["id"]

    response = client.get(f"/bilans/{bilan_id}/program").json()

    assert response["position"] == "seated"
    assert [item["zone"] for item in response["program"]] == ["neck", "lower_arm", "hand"]
    assert all(item["basis"] == "declared" for item in response["program"])
    assert response["program"][0]["capsule"]["id"] == "seated-neck-lateral-stretch"
    assert any("tâches saisies" in warning for warning in response["warnings"])


def test_every_library_metier_gets_a_program_without_any_video(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)

    for model in client.get("/metiers").json():
        bilan_id = client.post(f"/metiers/{model['id']}/bilan", json={}).json()["id"]
        program = client.get(f"/bilans/{bilan_id}/program").json()["program"]
        assert 1 <= len(program) <= 3, model["id"]


def test_bilan_program_stays_empty_without_video_and_without_tasks(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    bilan_id = client.post("/bilans", json={}).json()["id"]

    response = client.get(f"/bilans/{bilan_id}/program").json()

    assert response["program"] == []
    assert not any("tâches saisies" in warning for warning in response["warnings"])


def test_archive_and_restore_a_bilan_moves_it_between_the_two_lists(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    kept = client.post("/bilans", json={"label": "Gardé"}).json()["id"]
    old = client.post("/bilans", json={"label": "Ancien"}).json()["id"]

    archived = client.post(f"/bilans/{old}/archive")

    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert [b["id"] for b in client.get("/bilans").json()] == [kept]
    assert [b["id"] for b in client.get("/bilans?archived=true").json()] == [old]
    # Un bilan archivé reste lisible, avec ses fiches.
    assert client.get(f"/bilans/{old}").json()["archived_at"] is not None

    restored = client.post(f"/bilans/{old}/unarchive")

    assert restored.json()["archived_at"] is None
    assert {b["id"] for b in client.get("/bilans").json()} == {kept, old}
    assert client.get("/bilans?archived=true").json() == []


def test_archive_unknown_bilan_returns_404(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)

    assert client.post("/bilans/nope/archive").status_code == 404
    assert client.post("/bilans/nope/unarchive").status_code == 404


def test_delete_bilan_removes_its_tasks_but_keeps_the_analysis(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    _save_analysis_with_frames("a-1", _sawtooth_frames())
    client = TestClient(app)
    bilan_id = client.post("/bilans", json={"workday_hours": 9.0}).json()["id"]
    other = client.post("/bilans", json={"label": "Autre"}).json()["id"]
    client.post(f"/bilans/{bilan_id}/analyses",
                json={"analysis_id": "a-1", "activity_hours": 4.0, "representative": True})
    client.post(f"/bilans/{bilan_id}/tasks", json=_task_payload())

    response = client.delete(f"/bilans/{bilan_id}")

    assert response.status_code == 200
    assert response.json() == {"deleted": bilan_id}
    assert client.get(f"/bilans/{bilan_id}").status_code == 404
    assert [b["id"] for b in client.get("/bilans").json()] == [other]
    assert client.get("/analyses/a-1").status_code == 200
    # La vidéo peut être rattachée à un autre bilan.
    attach = client.post(f"/bilans/{other}/analyses",
                         json={"analysis_id": "a-1", "activity_hours": 4.0, "representative": True})
    assert attach.status_code == 200
    assert client.delete(f"/bilans/{bilan_id}").status_code == 404


def test_delete_an_archived_bilan(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    bilan_id = client.post("/bilans", json={}).json()["id"]
    client.post(f"/bilans/{bilan_id}/archive")

    assert client.delete(f"/bilans/{bilan_id}").status_code == 200
    assert client.get("/bilans?archived=true").json() == []


def test_an_existing_database_without_archiving_is_upgraded_in_place(tmp_path, monkeypatch):
    import duckdb

    path = tmp_path / "old.duckdb"
    old = duckdb.connect(str(path))
    old.execute(
        "CREATE TABLE bilans (id VARCHAR PRIMARY KEY, created_at TIMESTAMP NOT NULL, "
        "label VARCHAR, workday_hours DOUBLE NOT NULL)"
    )
    old.execute("INSERT INTO bilans VALUES ('b-1', '2026-01-01 10:00:00', 'Ancien bilan', 8.0)")
    old.close()
    monkeypatch.setattr(storage, "DB_PATH", path)
    client = TestClient(app)

    [bilan] = client.get("/bilans").json()

    assert bilan["id"] == "b-1" and bilan["archived_at"] is None
    assert client.post("/bilans/b-1/archive").json()["archived_at"] is not None


def test_folders_are_created_renamed_listed_and_names_stay_unique(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)

    acme = client.post("/bilan-folders", json={"name": "  Acme Industrie "})
    assert acme.status_code == 200 and acme.json()["name"] == "Acme Industrie"
    client.post("/bilan-folders", json={"name": "Boulangerie Roche"})

    assert [f["name"] for f in client.get("/bilan-folders").json()] == [
        "Acme Industrie", "Boulangerie Roche"]
    assert client.post("/bilan-folders", json={"name": "ACME industrie"}).status_code == 409
    assert client.post("/bilan-folders", json={"name": "   "}).status_code == 422
    assert client.post("/bilan-folders", json={"name": "x" * 81}).status_code == 422

    renamed = client.put(f"/bilan-folders/{acme.json()['id']}", json={"name": "Acme SA"})
    assert renamed.json()["name"] == "Acme SA"
    # Garder son propre nom (casse changée) est permis, prendre celui d'un autre non.
    assert client.put(f"/bilan-folders/{acme.json()['id']}", json={"name": "ACME sa"}).status_code == 200
    assert client.put(f"/bilan-folders/{acme.json()['id']}",
                      json={"name": "boulangerie roche"}).status_code == 409
    assert client.put("/bilan-folders/nope", json={"name": "Z"}).status_code == 404


def test_moving_bilans_between_folders_keeps_them_in_their_active_or_archive_list(
    tmp_path, monkeypatch
):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    folder = client.post("/bilan-folders", json={"name": "Acme"}).json()["id"]
    first = client.post("/bilans", json={"label": "Poste A"}).json()["id"]
    second = client.post("/bilans", json={"label": "Poste B"}).json()["id"]

    assert client.get(f"/bilans/{first}").json()["folder_id"] is None
    moved = client.post(f"/bilans/{first}/folder", json={"folder_id": folder})
    assert moved.status_code == 200 and moved.json()["folder_id"] == folder
    client.post(f"/bilans/{second}/folder", json={"folder_id": folder})
    client.post(f"/bilans/{second}/archive")

    active = {b["id"]: b["folder_id"] for b in client.get("/bilans").json()}
    archived = {b["id"]: b["folder_id"] for b in client.get("/bilans?archived=true").json()}
    assert active == {first: folder} and archived == {second: folder}

    out = client.post(f"/bilans/{first}/folder", json={"folder_id": None})
    assert out.json()["folder_id"] is None
    assert client.post(f"/bilans/{first}/folder", json={"folder_id": "nope"}).status_code == 404
    assert client.post("/bilans/nope/folder", json={"folder_id": folder}).status_code == 404


def test_deleting_a_folder_keeps_its_bilans(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    folder = client.post("/bilan-folders", json={"name": "Acme"}).json()["id"]
    bilan_id = client.post("/bilans", json={"label": "Poste A"}).json()["id"]
    client.post(f"/bilans/{bilan_id}/folder", json={"folder_id": folder})

    assert client.delete(f"/bilan-folders/{folder}").status_code == 200

    assert client.get("/bilan-folders").json() == []
    assert client.get(f"/bilans/{bilan_id}").json()["folder_id"] is None
    assert [b["id"] for b in client.get("/bilans").json()] == [bilan_id]
    assert client.delete(f"/bilan-folders/{folder}").status_code == 404


def test_duplicating_a_bilan_keeps_its_folder_but_not_its_archive_state(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    folder = client.post("/bilan-folders", json={"name": "Acme"}).json()["id"]
    bilan_id = client.post("/bilans", json={"label": "Poste A"}).json()["id"]
    client.post(f"/bilans/{bilan_id}/folder", json={"folder_id": folder})
    client.post(f"/bilans/{bilan_id}/archive")

    copy = client.post(f"/bilans/{bilan_id}/duplicate", json={}).json()

    assert copy["folder_id"] == folder
    assert copy["archived_at"] is None


def test_archiving_and_moving_a_bilan_that_has_tasks_and_a_video_works(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    _save_analysis_with_frames("a-1", _sawtooth_frames())
    client = TestClient(app)
    folder = client.post("/bilan-folders", json={"name": "Acme"}).json()["id"]
    bilan_id = client.post("/bilans", json={"label": "Poste A", "workday_hours": 9.0}).json()["id"]
    client.post(f"/bilans/{bilan_id}/analyses",
                json={"analysis_id": "a-1", "activity_hours": 4.0, "representative": True})
    client.post(f"/bilans/{bilan_id}/tasks", json=_task_payload())

    assert client.post(f"/bilans/{bilan_id}/archive").status_code == 200
    assert client.post(f"/bilans/{bilan_id}/folder", json={"folder_id": folder}).status_code == 200
    assert client.post(f"/bilans/{bilan_id}/unarchive").status_code == 200
    assert client.delete(f"/bilan-folders/{folder}").status_code == 200

    final = client.get(f"/bilans/{bilan_id}").json()
    assert len(final["tasks"]) == 1 and len(final["items"]) == 1
    assert final["folder_id"] is None and final["archived_at"] is None


def _folder(client, name, parent_id=None):
    response = client.post("/bilan-folders", json={"name": name, "parent_id": parent_id})
    assert response.status_code == 200, response.text
    return response.json()


def test_folders_nest_company_service_and_post(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    acme = _folder(client, "Acme")
    production = _folder(client, "Production", acme["id"])
    soudure = _folder(client, "Soudure", production["id"])
    bilan_id = client.post("/bilans", json={"label": "Poste soudeur"}).json()["id"]

    assert acme["parent_id"] is None and soudure["parent_id"] == production["id"]
    assert client.post(f"/bilans/{bilan_id}/folder", json={"folder_id": soudure["id"]}).json()[
        "folder_id"] == soudure["id"]
    assert {f["id"]: f["parent_id"] for f in client.get("/bilan-folders").json()} == {
        acme["id"]: None, production["id"]: acme["id"], soudure["id"]: production["id"]}


def test_folder_names_are_unique_per_parent_only(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    acme = _folder(client, "Acme")
    roche = _folder(client, "Roche")
    _folder(client, "Production", acme["id"])

    # Même nom sous un autre parent : permis. Même nom dans le même parent : refusé.
    _folder(client, "production", roche["id"])
    duplicate = client.post("/bilan-folders", json={"name": "PRODUCTION", "parent_id": acme["id"]})
    assert duplicate.status_code == 409
    assert client.post("/bilan-folders", json={"name": "acme"}).status_code == 409
    assert client.post("/bilan-folders", json={"name": "X", "parent_id": "nope"}).status_code == 404


def test_moving_a_folder_carries_its_content_and_refuses_cycles(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    acme = _folder(client, "Acme")
    production = _folder(client, "Production", acme["id"])
    soudure = _folder(client, "Soudure", production["id"])
    other = _folder(client, "Autre société")
    bilan_id = client.post("/bilans", json={"label": "Poste"}).json()["id"]
    client.post(f"/bilans/{bilan_id}/folder", json={"folder_id": soudure["id"]})

    moved = client.post(f"/bilan-folders/{production['id']}/move", json={"parent_id": other["id"]})

    assert moved.status_code == 200 and moved.json()["parent_id"] == other["id"]
    folders = {f["id"]: f["parent_id"] for f in client.get("/bilan-folders").json()}
    assert folders[soudure["id"]] == production["id"]
    assert client.get(f"/bilans/{bilan_id}").json()["folder_id"] == soudure["id"]
    # Cycles : dans lui-même, dans un de ses descendants.
    for target in (production["id"], soudure["id"]):
        refused = client.post(f"/bilan-folders/{production['id']}/move", json={"parent_id": target})
        assert refused.status_code == 422
    assert client.post(f"/bilan-folders/{production['id']}/move",
                       json={"parent_id": "nope"}).status_code == 404
    assert client.post("/bilan-folders/nope/move", json={"parent_id": None}).status_code == 404
    # Retour à la racine.
    root = client.post(f"/bilan-folders/{production['id']}/move", json={"parent_id": None})
    assert root.json()["parent_id"] is None


def test_moving_a_folder_onto_a_sibling_name_is_refused(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    acme = _folder(client, "Acme")
    roche = _folder(client, "Roche")
    _folder(client, "Production", acme["id"])
    other_production = _folder(client, "Production", roche["id"])

    refused = client.post(f"/bilan-folders/{other_production['id']}/move",
                          json={"parent_id": acme["id"]})

    assert refused.status_code == 409


def test_deleting_a_folder_moves_its_subfolders_and_bilans_up_one_level(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    acme = _folder(client, "Acme")
    production = _folder(client, "Production", acme["id"])
    soudure = _folder(client, "Soudure", production["id"])
    direct = client.post("/bilans", json={"label": "Chef d'atelier"}).json()["id"]
    client.post(f"/bilans/{direct}/folder", json={"folder_id": production["id"]})

    assert client.delete(f"/bilan-folders/{production['id']}").status_code == 200

    folders = {f["id"]: f["parent_id"] for f in client.get("/bilan-folders").json()}
    assert folders == {acme["id"]: None, soudure["id"]: acme["id"]}
    assert client.get(f"/bilans/{direct}").json()["folder_id"] == acme["id"]
    # Un dossier racine supprimé : son contenu va à la racine.
    assert client.delete(f"/bilan-folders/{acme['id']}").status_code == 200
    assert client.get(f"/bilans/{direct}").json()["folder_id"] is None
    assert [f["parent_id"] for f in client.get("/bilan-folders").json()] == [None]


def test_deleting_a_folder_is_refused_when_a_subfolder_would_clash_by_name(tmp_path, monkeypatch):
    _patch_db(tmp_path, monkeypatch)
    client = TestClient(app)
    acme = _folder(client, "Acme")
    production = _folder(client, "Production", acme["id"])
    _folder(client, "Soudure", production["id"])
    _folder(client, "Soudure", acme["id"])

    refused = client.delete(f"/bilan-folders/{production['id']}")

    assert refused.status_code == 409
    assert len(client.get("/bilan-folders").json()) == 4


def test_an_existing_folder_table_without_parent_is_upgraded_in_place(tmp_path, monkeypatch):
    import duckdb

    path = tmp_path / "old.duckdb"
    old = duckdb.connect(str(path))
    old.execute("CREATE TABLE bilan_folders (id VARCHAR PRIMARY KEY, created_at TIMESTAMP NOT NULL, "
                "name VARCHAR NOT NULL)")
    old.execute("INSERT INTO bilan_folders VALUES ('f-1', '2026-01-01 10:00:00', 'Acme')")
    old.close()
    monkeypatch.setattr(storage, "DB_PATH", path)
    client = TestClient(app)

    [folder] = client.get("/bilan-folders").json()

    assert folder["name"] == "Acme" and folder["parent_id"] is None
    assert _folder(client, "Production", "f-1")["parent_id"] == "f-1"
