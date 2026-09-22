import tempfile
from pathlib import Path

import cv2
import numpy as np
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
