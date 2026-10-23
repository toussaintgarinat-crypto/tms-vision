import re

from fastapi.testclient import TestClient

from tms_vision import version
from tms_vision.api import app


def test_version_file_holds_a_semantic_version():
    assert re.fullmatch(r"\d+\.\d+\.\d+", version.get_version())


def test_version_is_unknown_when_file_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(version, "VERSION_FILE", tmp_path / "VERSION")
    assert version.get_version() == version.UNKNOWN


def test_version_route_returns_the_version():
    response = TestClient(app).get("/version")
    assert response.status_code == 200
    assert response.json() == {"version": version.get_version()}
