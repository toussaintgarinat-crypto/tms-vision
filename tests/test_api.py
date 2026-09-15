import json
import tempfile
from pathlib import Path

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


def test_create_analysis_rejects_negative_load_kg(tmp_path, monkeypatch):
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


def test_output_files_are_actually_served_at_returned_urls(tmp_path, monkeypatch):
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


def test_create_analysis_cleans_up_temp_file_when_upload_copy_fails(tmp_path, monkeypatch):
    """Régression pour 9d6a9da : avant le fix, `upload_path = Path(tmp.name)`
    n'était assigné qu'APRÈS `shutil.copyfileobj(...)`, et tout cela se
    trouvait hors du try/finally qui appelle `upload_path.unlink(...)`. Si la
    copie échouait, le fichier temporaire restait donc orphelin sur disque.
    Ici on force l'échec de la copie (sans avoir besoin de vraiment remplir
    le disque) et on vérifie que le fichier temporaire créé par
    tempfile.NamedTemporaryFile ne survit pas à la requête, quel que soit le
    point d'échec."""
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

    # L'OSError levée n'est pas parmi (FileNotFoundError, RuntimeError) que
    # l'endpoint intercepte lui-même : elle remonte donc telle quelle.
    # raise_server_exceptions=False permet d'obtenir une vraie réponse HTTP
    # (500) plutôt que de voir l'exception se propager dans le test.
    client = TestClient(app, raise_server_exceptions=False)
    with open(video_path, "rb") as video_file:
        response = client.post(
            "/analyses",
            files={"file": ("synthetic.mp4", video_file, "video/mp4")},
            data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
        )

    assert response.status_code == 500
    assert len(created_paths) == 1
    assert not created_paths[0].exists(), (
        f"Le fichier temporaire {created_paths[0]} aurait dû être supprimé "
        "par le `finally: upload_path.unlink(...)` de create_analysis même "
        "quand la copie échoue."
    )


def test_get_output_returns_404_for_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    response = client.get("/outputs/does-not-exist.mp4")

    assert response.status_code == 404


def test_start_upload_creates_session_with_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    response = client.post(
        "/uploads",
        data={"filename": "clip.mp4", "total_chunks": "3"},
    )

    assert response.status_code == 200
    upload_id = response.json()["upload_id"]
    meta_path = tmp_path / ".uploads" / upload_id / "meta.json"
    assert meta_path.is_file()
    assert json.loads(meta_path.read_text()) == {"filename": "clip.mp4", "total_chunks": 3}


def test_start_upload_rejects_zero_total_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    response = client.post(
        "/uploads",
        data={"filename": "clip.mp4", "total_chunks": "0"},
    )

    assert response.status_code == 422


def test_upload_chunk_writes_chunk_file(tmp_path, monkeypatch):
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
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    response = client.put(
        "/uploads/does-not-exist/chunks/0",
        files={"file": ("chunk-0", b"hello", "application/octet-stream")},
    )

    assert response.status_code == 404


def test_upload_chunk_rejects_out_of_range_index(tmp_path, monkeypatch):
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
    assert body["summary"]["detected_frame_count"] == 0
    assert body["summary"]["max_score"] == 0
    assert body["annotated_video_url"].startswith("/outputs/")
    assert body["csv_url"].startswith("/outputs/")

    # La session est nettoyée après complétion, réussie ou pas.
    assert not (tmp_path / ".uploads" / upload_id).exists()


def test_chunks_reassembled_by_index_regardless_of_arrival_order(tmp_path, monkeypatch):
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    video_path = tmp_path / "synthetic.mp4"
    _write_synthetic_video(video_path)
    video_bytes = video_path.read_bytes()
    midpoint = len(video_bytes) // 2
    chunks = [video_bytes[:midpoint], video_bytes[midpoint:]]

    client = TestClient(app)
    start_response = client.post(
        "/uploads", data={"filename": "synthetic.mp4", "total_chunks": "2"}
    )
    upload_id = start_response.json()["upload_id"]

    # Chunk 1 envoyé avant chunk 0 : l'ordre d'arrivée est inversé par rapport
    # à l'ordre d'index. La réassemblage doit suivre l'index, pas l'arrivée.
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
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    start_response = client.post("/uploads", data={"filename": "clip.mp4", "total_chunks": "2"})
    upload_id = start_response.json()["upload_id"]

    # Seul le chunk 0 est envoyé ; le chunk 1 manque.
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
    monkeypatch.setattr("tms_vision.api.OUTPUT_DIR", tmp_path)

    client = TestClient(app)
    response = client.post(
        "/uploads/does-not-exist/complete",
        data={"side": "right", "load_kg": "0", "wrist_twist": "normal"},
    )

    assert response.status_code == 404
