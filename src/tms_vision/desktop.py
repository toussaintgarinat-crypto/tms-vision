"""Application de bureau : lance l'API et le site sur le poste du praticien et ouvre le navigateur.

C'est le point d'entrée de l'exécutable construit par deploy/desktop (PyInstaller). Tout reste sur
l'ordinateur : l'API écoute sur 127.0.0.1 seulement, les données sont dans le dossier de l'utilisateur
(pas dans le dossier d'installation, pour survivre aux mises à jour) :

  Windows  %APPDATA%\\TMS Vision
  macOS    ~/Library/Application Support/TMS Vision
  Linux    ~/.local/share/tms-vision

Le site est servi par un Node.js embarqué (dossier `node/`), le site compilé est dans `web/`. En
développement, `python -m tms_vision.desktop --web-dir web/.next/standalone` fait la même chose avec
le Node.js du système."""
import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from tms_vision.paths import resource_root

# Ports peu courants, pour ne pas entrer en conflit avec un autre outil du poste. Le port de l'API
# est figé dans le site au moment de sa construction (NEXT_PUBLIC_API_URL, voir deploy/desktop).
API_PORT = 18000
WEB_PORT = 13000
HOST = "127.0.0.1"
START_TIMEOUT_SECONDS = 90


def data_dir() -> Path:
    """Dossier des données de l'utilisateur (base d'analyses, vidéos, réglages)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / "TMS Vision"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "TMS Vision"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "tms-vision"


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((HOST, port)) == 0


def is_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status < 500
    except OSError:
        return False


def find_node(root: Path) -> str | None:
    bundled = root / "node" / ("node.exe" if sys.platform == "win32" else "node")
    if bundled.is_file():
        return str(bundled)
    return shutil.which("node")


def find_ffmpeg() -> str | None:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001 - absent ou illisible : on retombe sur le ffmpeg du système
        return shutil.which("ffmpeg")


def find_web_dir(root: Path, explicit: str | None) -> Path | None:
    for candidate in ([Path(explicit)] if explicit else []) + [root / "web"]:
        if (candidate / "server.js").is_file():
            return candidate
    return None


class Application:
    """Les deux serveurs (API dans ce processus, site dans un sous-processus Node.js)."""

    def __init__(self, directory: Path, web_dir: Path, node: str):
        self.directory = directory
        self.web_dir = web_dir
        self.node = node
        self.web_process: subprocess.Popen | None = None
        self.api_server = None
        self.api_thread: threading.Thread | None = None
        self.url = f"http://{HOST}:{WEB_PORT}"

    def start(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        # L'API écrit dans `data/` et `outputs/` relativement au dossier courant.
        os.chdir(self.directory)
        os.environ["TMS_CHECK_UPDATES"] = "1"
        os.environ.setdefault("ALLOWED_ORIGINS", f"http://{HOST}:{WEB_PORT},http://localhost:{WEB_PORT}")
        ffmpeg = find_ffmpeg()
        if ffmpeg:
            os.environ.setdefault("TMS_FFMPEG", ffmpeg)

        import uvicorn

        from tms_vision.api import app

        config = uvicorn.Config(app, host=HOST, port=API_PORT, log_level="warning", log_config=None)
        self.api_server = uvicorn.Server(config)
        self.api_thread = threading.Thread(target=self.api_server.run, daemon=True)
        self.api_thread.start()

        logs = self.directory / "logs"
        logs.mkdir(exist_ok=True)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.web_process = subprocess.Popen(
            [self.node, "server.js"], cwd=self.web_dir, creationflags=flags,
            env={**os.environ, "PORT": str(WEB_PORT), "HOSTNAME": HOST, "NODE_ENV": "production"},
            stdout=open(logs / "site.log", "ab"), stderr=subprocess.STDOUT,
        )

    def wait_until_ready(self) -> bool:
        deadline = time.monotonic() + START_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if self.web_process is not None and self.web_process.poll() is not None:
                return False
            if is_ready(f"http://{HOST}:{API_PORT}/version") and is_ready(self.url):
                return True
            time.sleep(0.5)
        return False

    def stop(self) -> None:
        if self.web_process is not None and self.web_process.poll() is None:
            self.web_process.terminate()
            try:
                self.web_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.web_process.kill()
        if self.api_server is not None:
            self.api_server.should_exit = True
        if self.api_thread is not None:
            self.api_thread.join(timeout=5)


def open_folder(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 - dossier choisi par l'application
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def show_window(app: Application) -> None:
    """Petite fenêtre : état, ouvrir le site, ouvrir le dossier des données, quitter."""
    import tkinter as tk
    from tkinter import ttk

    from tms_vision import updates, version

    root = tk.Tk()
    root.title("TMS Vision")
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=16)
    frame.grid()
    ttk.Label(frame, text=f"TMS Vision {version.get_version()}", font=("TkDefaultFont", 14, "bold")).grid(
        sticky="w"
    )
    status = tk.StringVar(value="Démarrage… (quelques secondes)")
    ttk.Label(frame, textvariable=status, wraplength=320).grid(sticky="w", pady=(8, 12))
    buttons = ttk.Frame(frame)
    buttons.grid(sticky="w")
    open_button = ttk.Button(buttons, text="Ouvrir TMS Vision", command=lambda: webbrowser.open(app.url))
    open_button.grid(row=0, column=0, padx=(0, 8))
    open_button.state(["disabled"])
    ttk.Button(buttons, text="Dossier des données", command=lambda: open_folder(app.directory)).grid(
        row=0, column=1, padx=(0, 8)
    )
    ttk.Button(buttons, text="Quitter", command=root.destroy).grid(row=0, column=2)
    update_text = tk.StringVar(value="")
    update_label = ttk.Label(frame, textvariable=update_text, foreground="#b45309")
    update_label.grid(sticky="w", pady=(10, 0))
    update_button = ttk.Button(frame, text="Télécharger la mise à jour")
    update_button.grid(sticky="w", pady=(4, 0))
    update_button.grid_remove()
    ttk.Label(
        frame,
        text="Fermez cette fenêtre (Quitter) pour arrêter l'application.\nVos données restent sur cet ordinateur.",
        foreground="#555",
    ).grid(sticky="w", pady=(12, 0))

    def boot() -> None:
        ready = app.wait_until_ready()

        def done() -> None:
            if ready:
                status.set(f"Prêt : {app.url}")
                open_button.state(["!disabled"])
                webbrowser.open(app.url)
            else:
                status.set(f"Le démarrage a échoué. Détails dans {app.directory / 'logs'}.")

        root.after(0, done)

    def look_for_update() -> None:
        result = updates.check(version.get_version())

        def show() -> None:
            if result["available"]:
                update_text.set(f"Une nouvelle version est disponible : {result['version']}")
                update_button.configure(command=lambda: webbrowser.open(result["url"]))
                update_button.grid()

        if result["available"]:
            root.after(0, show)

    threading.Thread(target=boot, daemon=True).start()
    threading.Thread(target=look_for_update, daemon=True).start()
    root.mainloop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tms-vision", description="Application TMS Vision de bureau.")
    parser.add_argument("--no-window", action="store_true", help="sans fenêtre (Ctrl+C pour arrêter)")
    parser.add_argument("--no-browser", action="store_true", help="n'ouvre pas le navigateur")
    parser.add_argument("--web-dir", help="dossier du site compilé (contient server.js)")
    parser.add_argument("--data-dir", help="dossier des données (par défaut : celui de l'utilisateur)")
    args = parser.parse_args(argv)

    root = resource_root()
    directory = Path(args.data_dir) if args.data_dir else data_dir()
    web_dir = find_web_dir(root, args.web_dir)
    node = find_node(root)
    if web_dir is None or node is None:
        print("Installation incomplète : site web ou Node.js introuvable.", file=sys.stderr)
        return 2

    # Déjà lancée : on rouvre simplement le navigateur au lieu de lancer une seconde copie.
    if port_in_use(WEB_PORT) and is_ready(f"http://{HOST}:{WEB_PORT}"):
        if not args.no_browser:
            webbrowser.open(f"http://{HOST}:{WEB_PORT}")
        return 0
    if port_in_use(API_PORT) or port_in_use(WEB_PORT):
        print(f"Les ports {API_PORT} et {WEB_PORT} doivent être libres.", file=sys.stderr)
        return 3

    directory.mkdir(parents=True, exist_ok=True)
    if getattr(sys, "frozen", False):
        # Sans console (fenêtre seule), stdout/stderr n'existent pas : on écrit dans un journal.
        (directory / "logs").mkdir(exist_ok=True)
        sys.stdout = sys.stderr = open(directory / "logs" / "application.log", "a", encoding="utf-8")

    app = Application(directory, web_dir, node)
    app.start()
    try:
        if args.no_window:
            ready = app.wait_until_ready()
            print(f"{'Prêt' if ready else 'Échec du démarrage'} : {app.url}", flush=True, file=sys.__stdout__)
            if ready and not args.no_browser:
                webbrowser.open(app.url)
            while ready:
                time.sleep(1)
            return 0 if ready else 1
        try:
            show_window(app)
        except ImportError:
            # tkinter absent : même chose sans fenêtre.
            app.wait_until_ready() and webbrowser.open(app.url)
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        app.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
