import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tms_vision import storage
from tms_vision.api import app
from tms_vision.pose_models import wholebody_setup as ws


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Réglages dans un dossier temporaire, état de téléchargement remis à zéro, cache simulé."""
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "data" / "test.duckdb")
    monkeypatch.delenv("TMS_WHOLEBODY_MODE", raising=False)
    monkeypatch.setattr(ws, "_download", {"state": "idle", "message": None})
    cache = tmp_path / "cache"
    monkeypatch.setattr(
        ws, "weights_paths",
        lambda mode: [(f"https://example.test/{mode}-det.zip", cache / f"{mode}-det.onnx"),
                      (f"https://example.test/{mode}-pose.zip", cache / f"{mode}-pose.onnx")],
    )
    monkeypatch.setattr(ws, "dependencies_available", lambda: True)
    return cache


def _write_weights(cache: Path, mode: str):
    cache.mkdir(parents=True, exist_ok=True)
    for kind in ("det", "pose"):
        (cache / f"{mode}-{kind}.onnx").write_bytes(b"onnx")


def test_mode_defaults_then_follows_env_then_site_choice(monkeypatch):
    assert ws.get_mode() == "performance"
    monkeypatch.setenv("TMS_WHOLEBODY_MODE", "balanced")  # installations existantes
    assert ws.get_mode() == "balanced"
    ws.set_mode("lightweight")  # le choix fait sur le site l'emporte
    assert ws.get_mode() == "lightweight"
    with pytest.raises(ValueError):
        ws.set_mode("turbo")
    monkeypatch.setenv("TMS_WHOLEBODY_MODE", "n'importe quoi")
    (storage.DB_PATH.parent / "pose_models.json").write_text("pas du json")
    assert ws.get_mode() == "performance"  # fichier illisible et variable invalide : défaut sûr


def test_weights_ready_needs_both_files_and_depends_on_the_mode(isolated):
    assert ws.weights_ready("performance") is False
    (isolated).mkdir(parents=True)
    (isolated / "performance-det.onnx").write_bytes(b"onnx")
    assert ws.weights_ready("performance") is False  # il en manque un
    (isolated / "performance-pose.onnx").write_bytes(b"onnx")
    assert ws.weights_ready("performance") is True
    assert ws.weights_ready("balanced") is False


def test_weights_never_ready_without_packages(isolated, monkeypatch):
    _write_weights(isolated, "performance")
    monkeypatch.setattr(ws, "dependencies_available", lambda: False)
    assert ws.weights_ready("performance") is False
    assert ws.status()["available"] is False


def _fake_rtmlib(monkeypatch, behavior):
    import sys, types

    module = types.ModuleType("rtmlib.tools.file")
    module.download_checkpoint = behavior
    monkeypatch.setitem(sys.modules, "rtmlib", types.ModuleType("rtmlib"))
    monkeypatch.setitem(sys.modules, "rtmlib.tools", types.ModuleType("rtmlib.tools"))
    monkeypatch.setitem(sys.modules, "rtmlib.tools.file", module)


def _wait(state):
    for _ in range(100):
        if ws.status()["download"]["state"] == state:
            return
        time.sleep(0.02)
    raise AssertionError(f"état {state!r} non atteint : {ws.status()['download']}")


def test_download_runs_in_background_and_ends_ready(isolated, monkeypatch):
    calls = []

    def download(url, progress=True):
        calls.append((url, progress))
        _write_weights(isolated, "performance")

    _fake_rtmlib(monkeypatch, download)
    assert ws.start_download() is True
    _wait("idle")  # prêt : l'état « terminé » est masqué par weights_ready
    assert ws.status()["weights_ready"] is True
    assert [c[0] for c in calls] == ["https://example.test/performance-det.zip", "https://example.test/performance-pose.zip"]
    assert all(progress is False for _, progress in calls)


def test_download_failure_is_reported_not_raised(isolated, monkeypatch):
    def download(url, progress=True):
        raise OSError("réseau coupé")

    _fake_rtmlib(monkeypatch, download)
    ws.start_download()
    _wait("error")
    status = ws.status()
    assert "réseau coupé" in status["download"]["message"] and status["weights_ready"] is False
    assert ws.start_download() is True  # on peut réessayer


def test_second_download_is_refused_while_one_runs(isolated, monkeypatch):
    import threading

    gate = threading.Event()

    def download(url, progress=True):
        gate.wait(2)
        _write_weights(isolated, "performance")

    _fake_rtmlib(monkeypatch, download)
    assert ws.start_download() is True
    assert ws.start_download() is False
    assert ws.status()["download"]["state"] == "running"
    gate.set()
    _wait("idle")


def test_api_status_mode_and_install(isolated, monkeypatch):
    client = TestClient(app)
    status = client.get("/pose-models/wholebody").json()
    assert status["available"] and status["weights_ready"] is False and status["mode"] == "performance"
    assert [m["id"] for m in status["modes"]] == ["performance", "balanced", "lightweight"]

    assert client.put("/pose-models/wholebody", json={"mode": "balanced"}).json()["mode"] == "balanced"
    assert client.put("/pose-models/wholebody", json={"mode": "turbo"}).status_code == 422

    started = []
    monkeypatch.setattr(ws, "start_download", lambda mode=None: started.append(mode) or True)
    client.post("/pose-models/wholebody/install")
    assert started == [None]
    _write_weights(isolated, "balanced")
    client.post("/pose-models/wholebody/install")
    assert len(started) == 1  # déjà prêt : rien à retélécharger


def test_api_install_without_packages_returns_422(monkeypatch):
    monkeypatch.setattr(ws, "dependencies_available", lambda: False)
    response = TestClient(app).post("/pose-models/wholebody/install")
    assert response.status_code == 422 and "pas installé" in response.json()["detail"]
