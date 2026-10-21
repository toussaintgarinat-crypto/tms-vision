import tempfile
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from tms_vision import storage
from tms_vision.api import app


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
    assert {e["zone"] for e in body} == {"neck", "trunk", "upper_arm", "lower_arm"}
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
