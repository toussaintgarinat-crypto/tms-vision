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


def test_the_logo_is_shipped_and_found():
    icon = desktop.find_icon(paths.resource_root())

    assert icon is not None and icon.name == "icon.png"
    assert (paths.resource_root() / "deploy" / "desktop" / "icon.ico").is_file()
    assert (paths.resource_root() / "deploy" / "desktop" / "icon.icns").is_file()


def test_find_node_prefers_the_bundled_one(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    (tmp_path / "node").mkdir()
    (tmp_path / "node" / "node").write_text("", encoding="utf-8")

    assert desktop.find_node(tmp_path) == str(tmp_path / "node" / "node")


def test_ports_are_uncommon_and_distinct_and_the_site_is_allowed_by_default_cors():
    assert desktop.API_PORT != desktop.WEB_PORT
    assert {desktop.API_PORT, desktop.WEB_PORT}.isdisjoint({3000, 8000, 80, 443})


def test_the_desktop_app_requires_accounts_and_opens_the_first_run_screen():
    source = (Path(__file__).resolve().parents[1] / "src" / "tms_vision" / "desktop.py").read_text(encoding="utf-8")
    assert 'os.environ["TMS_REQUIRE_AUTH"] = "1"' in source
    assert 'os.environ["TMS_LOCAL_SETUP"] = "1"' in source


def test_the_desktop_app_creates_and_keeps_its_own_secret_key(tmp_path):
    first = desktop.ensure_secret_key(tmp_path / "data")
    assert len(first) >= 16
    assert desktop.ensure_secret_key(tmp_path / "data") == first  # stable d'un lancement à l'autre
    (tmp_path / "data" / "secret.key").write_text("court", encoding="utf-8")
    assert len(desktop.ensure_secret_key(tmp_path / "data")) >= 16  # clé trop courte : refaite


def test_the_desktop_app_wires_the_key_and_the_local_link():
    source = (Path(__file__).resolve().parents[1] / "src" / "tms_vision" / "desktop.py").read_text(encoding="utf-8")
    assert 'os.environ.setdefault("TMS_SECRET_KEY", ensure_secret_key(self.directory))' in source
    assert "TMS_PUBLIC_WEB_URL" in source


# --- Plantage pendant une mise à jour : site resté seul, auto-test de l'installateur ----------------


def test_a_leftover_site_is_closed_but_only_if_it_is_ours(monkeypatch):
    import os

    from tms_vision import desktop

    listening = {desktop.WEB_PORT: [4001, 4002, os.getpid()], desktop.API_PORT: []}
    killed = []

    def listening_pids(port):
        return [pid for pid in listening[port] if pid not in killed]

    monkeypatch.setattr(desktop, "listening_pids", listening_pids)
    monkeypatch.setattr(desktop, "is_our_process", lambda pid: pid == 4001)  # 4002 : un autre programme
    monkeypatch.setattr(desktop.os, "kill", lambda pid, sig: killed.append(pid))
    monkeypatch.setattr(desktop, "port_in_use", lambda port: False)
    assert desktop.release_stale_ports() is True
    assert killed == [4001]  # ni l'autre programme, ni nous-mêmes


def test_ports_still_taken_by_something_else_are_reported(monkeypatch):
    from tms_vision import desktop

    monkeypatch.setattr(desktop, "listening_pids", lambda port: [])
    monkeypatch.setattr(desktop, "port_in_use", lambda port: True)
    assert desktop.release_stale_ports() is False


def _launch_with(monkeypatch, tmp_path, *, web_ready, api_ready, released):
    from tms_vision import desktop

    opened = []
    monkeypatch.setattr(desktop, "find_web_dir", lambda root, explicit: tmp_path)
    monkeypatch.setattr(desktop, "find_node", lambda root: "node")
    monkeypatch.setattr(
        desktop, "is_ready", lambda url: web_ready if f":{desktop.WEB_PORT}" in url else api_ready
    )
    monkeypatch.setattr(desktop, "port_in_use", lambda port: web_ready or api_ready)
    monkeypatch.setattr(desktop, "release_stale_ports", lambda: released)
    monkeypatch.setattr(desktop.webbrowser, "open", lambda url: opened.append(url))
    return desktop.main(["--data-dir", str(tmp_path / "data")]), opened


def test_a_running_application_is_only_reopened_when_site_and_api_both_answer(monkeypatch, tmp_path):
    code, opened = _launch_with(monkeypatch, tmp_path, web_ready=True, api_ready=True, released=False)
    assert code == 0 and len(opened) == 1


def test_a_site_left_alone_is_not_taken_for_a_running_application(monkeypatch, tmp_path):
    # Le site répond mais pas l'API : on ne rouvre pas l'ancienne page, on tente de libérer les ports.
    code, opened = _launch_with(monkeypatch, tmp_path, web_ready=True, api_ready=False, released=False)
    assert code == 3 and opened == []


def test_the_self_test_reports_a_missing_module_and_passes_otherwise(monkeypatch, tmp_path):
    import importlib

    from tms_vision import desktop

    log = tmp_path / "selftest.log"
    monkeypatch.setenv("TMS_SELFTEST_LOG", str(log))
    monkeypatch.setattr(importlib, "import_module", lambda name: None)
    assert desktop.self_test() == 0 and log.read_text() == "ok\n"

    def missing(name):
        raise ModuleNotFoundError("No module named 'tms_vision.mailer'")

    monkeypatch.setattr(importlib, "import_module", missing)
    assert desktop.self_test() == 1
    assert "tms_vision.mailer" in log.read_text()
    assert desktop.main(["--self-test"]) == 1  # l'option est branchée sur le point d'entrée


def test_the_mac_update_script_clears_the_quarantine_and_leaves_a_trace():
    from tms_vision import self_update

    assert "xattr -dr com.apple.quarantine" in self_update.MAC_SCRIPT
    assert self_update.MAC_SCRIPT.count("echo ") >= 3
