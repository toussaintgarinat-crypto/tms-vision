import sys
from pathlib import Path

from tms_vision import desktop, paths


def test_resource_root_is_the_repository_in_development_and_the_bundle_when_frozen(monkeypatch):
    assert (paths.resource_root() / "exercises").is_dir()
    assert (paths.resource_root() / "metiers").is_dir()

    monkeypatch.setattr(sys, "_MEIPASS", "/opt/tms", raising=False)

    assert paths.resource_root() == Path("/opt/tms")


def test_data_dir_is_outside_the_install_folder_and_per_platform(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert desktop.data_dir() == tmp_path / "TMS Vision"

    monkeypatch.setattr(sys, "platform", "darwin")
    assert desktop.data_dir() == Path.home() / "Library" / "Application Support" / "TMS Vision"

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert desktop.data_dir() == tmp_path / "tms-vision"


def test_find_web_dir_needs_a_built_site(tmp_path):
    assert desktop.find_web_dir(tmp_path, None) is None

    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "server.js").write_text("", encoding="utf-8")

    assert desktop.find_web_dir(tmp_path, None) == tmp_path / "web"
    assert desktop.find_web_dir(tmp_path / "ailleurs", str(tmp_path / "web")) == tmp_path / "web"


def test_find_node_prefers_the_bundled_one(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    (tmp_path / "node").mkdir()
    (tmp_path / "node" / "node").write_text("", encoding="utf-8")

    assert desktop.find_node(tmp_path) == str(tmp_path / "node" / "node")


def test_ports_are_uncommon_and_distinct_and_the_site_is_allowed_by_default_cors():
    assert desktop.API_PORT != desktop.WEB_PORT
    assert {desktop.API_PORT, desktop.WEB_PORT}.isdisjoint({3000, 8000, 80, 443})
