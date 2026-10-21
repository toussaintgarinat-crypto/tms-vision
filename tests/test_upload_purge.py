"""Les morceaux d'une session d'envoi abandonnée contiennent la vidéo BRUTE (visages nets) : ils
ne doivent pas rester sur le disque indéfiniment."""
import os
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from tms_vision import api
from tms_vision.api import UPLOAD_SESSION_MAX_AGE_SECONDS, _purge_stale_upload_sessions, app

HOUR = 3600


@pytest.fixture
def output_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "OUTPUT_DIR", tmp_path)
    return tmp_path


def make_session(output_dir, age_seconds, with_chunk=True, name=None):
    session = output_dir / ".uploads" / (name or uuid.uuid4().hex)
    session.mkdir(parents=True)
    (session / "meta.json").write_text("{}")
    if with_chunk:
        (session / "chunk_000000").write_bytes(b"video brute")
    moment = time.time() - age_seconds
    for path in [*session.iterdir(), session]:
        os.utime(path, (moment, moment))
    return session


def test_a_session_older_than_the_limit_is_deleted_with_its_chunks(output_dir):
    stale = make_session(output_dir, UPLOAD_SESSION_MAX_AGE_SECONDS + HOUR)

    _purge_stale_upload_sessions()

    assert not stale.exists()


def test_a_recent_session_is_kept(output_dir):
    recent = make_session(output_dir, HOUR)

    _purge_stale_upload_sessions()

    assert (recent / "chunk_000000").read_bytes() == b"video brute"


def test_a_session_still_receiving_chunks_is_kept_even_if_it_started_long_ago(output_dir):
    session = make_session(output_dir, UPLOAD_SESSION_MAX_AGE_SECONDS + HOUR)
    (session / "chunk_000001").write_bytes(b"morceau tout frais")  # activité récente

    _purge_stale_upload_sessions()

    assert session.exists()


def test_only_session_folders_named_like_uuids_are_ever_touched(output_dir):
    foreign = make_session(output_dir, UPLOAD_SESSION_MAX_AGE_SECONDS + HOUR, name="important")
    stray_file = output_dir / ".uploads" / "notes.txt"
    stray_file.write_text("ne pas supprimer")
    old = time.time() - UPLOAD_SESSION_MAX_AGE_SECONDS - HOUR
    os.utime(stray_file, (old, old))

    _purge_stale_upload_sessions()

    assert foreign.exists()
    assert stray_file.exists()


def test_a_missing_uploads_folder_is_not_an_error(output_dir):
    _purge_stale_upload_sessions()  # ne lève pas


def test_the_purge_returns_how_many_sessions_it_removed(output_dir):
    make_session(output_dir, UPLOAD_SESSION_MAX_AGE_SECONDS + HOUR)
    make_session(output_dir, UPLOAD_SESSION_MAX_AGE_SECONDS + 2 * HOUR)
    make_session(output_dir, HOUR)

    assert _purge_stale_upload_sessions() == 2


def test_starting_a_new_upload_cleans_up_abandoned_sessions(output_dir):
    stale = make_session(output_dir, UPLOAD_SESSION_MAX_AGE_SECONDS + HOUR)

    response = TestClient(app).post("/uploads", data={"filename": "clip.mp4", "total_chunks": "2"})

    assert response.status_code == 200
    assert not stale.exists()
    assert (output_dir / ".uploads" / response.json()["upload_id"] / "meta.json").is_file()


def test_the_api_purges_abandoned_sessions_at_startup(output_dir):
    stale = make_session(output_dir, UPLOAD_SESSION_MAX_AGE_SECONDS + HOUR)

    with TestClient(app):  # le « with » exécute le démarrage de l'application
        pass

    assert not stale.exists()
