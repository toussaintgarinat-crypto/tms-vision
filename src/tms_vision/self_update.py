"""Mise à jour en un clic de l'application de bureau : sauvegarde des données, téléchargement de
l'installateur publié sur GitHub (Releases), installation puis relance.

Les données de l'application de bureau sont dans le dossier de l'utilisateur, pas dans le dossier
d'installation : l'installateur n'y touche pas. Une copie de sauvegarde (`backups/`) est faite quand
même avant chaque mise à jour. Seule l'application construite (PyInstaller) peut se mettre à jour ;
lancée depuis le dépôt, elle garde le simple lien de téléchargement."""
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from tms_vision import updates, version

# Seuls les fichiers publiés par ce dépôt sont téléchargés.
DOWNLOAD_PREFIX = "https://github.com/toussaintgarinat-crypto/tms-vision/releases/download/"
KEEP_BACKUPS = 5
CHUNK = 1024 * 256

_lock = threading.Lock()
_state: dict = {"step": "idle", "message": "", "progress": None}
# Branché par desktop.py : arrête les serveurs et ferme l'application (l'installateur prend le relais).
quit_handler: Callable[[], None] | None = None
# Dossier des données, renseigné par desktop.py.
data_directory: Path | None = None


def status() -> dict:
    with _lock:
        return dict(_state)


def _set(step: str, message: str = "", progress: float | None = None) -> None:
    with _lock:
        _state.update(step=step, message=message, progress=progress)


def is_installable() -> bool:
    """Application construite, sur un système pris en charge, avec un dossier de données connu."""
    return bool(getattr(sys, "frozen", False)) and sys.platform in ("win32", "darwin") and data_directory is not None


def pick_asset(assets: list[dict], platform_name: str, machine: str) -> dict | None:
    """Fichier à installer : l'installateur Windows, ou le .dmg du Mac (Apple Silicon ou Intel)."""
    if platform_name == "win32":
        wanted = lambda name: name.endswith("Setup.exe")  # noqa: E731
    elif platform_name == "darwin":
        label = "Apple-Silicon" if machine.lower() in ("arm64", "aarch64") else "Intel"
        wanted = lambda name: name.endswith(f"{label}.dmg")  # noqa: E731
    else:
        return None
    for asset in assets:
        if wanted(asset["name"]) and asset["url"].startswith(DOWNLOAD_PREFIX):
            return asset
    return None


def backup_data(directory: Path, current_version: str, *, now: float | None = None) -> Path | None:
    """Copie zip de `data/` dans `backups/` (les 5 dernières sont gardées). None si rien à copier."""
    source = directory / "data"
    if not source.is_dir():
        return None
    backups = directory / "backups"
    backups.mkdir(exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H%M%S", time.localtime(now))
    target = backups / f"tms-data-avant-maj-{current_version}-{stamp}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(directory).as_posix())
    old = sorted(backups.glob("tms-data-avant-maj-*.zip"))[:-KEEP_BACKUPS]
    for path in old:
        path.unlink(missing_ok=True)
    return target


def download(asset: dict, destination: Path, on_progress: Callable[[float | None], None]) -> None:
    """Télécharge le fichier puis vérifie sa taille et, si GitHub la donne, son empreinte SHA-256."""
    request = urllib.request.Request(asset["url"], headers={"User-Agent": "tms-vision"})
    sha = hashlib.sha256()
    received = 0
    with urllib.request.urlopen(request, timeout=30) as response, open(destination, "wb") as out:
        total = asset.get("size") or int(response.headers.get("Content-Length") or 0) or None
        while chunk := response.read(CHUNK):
            out.write(chunk)
            sha.update(chunk)
            received += len(chunk)
            on_progress(received / total if total else None)
    if asset.get("size") and received != asset["size"]:
        raise OSError("téléchargement incomplet")
    digest = asset.get("digest") or ""
    if digest.startswith("sha256:") and digest[7:].lower() != sha.hexdigest():
        raise OSError("fichier téléchargé corrompu (empreinte différente)")


MAC_SCRIPT = r"""
pid="$1"; dmg="$2"; app="$3"
while kill -0 "$pid" 2>/dev/null; do sleep 0.5; done
mnt="$(mktemp -d)"
if hdiutil attach -nobrowse -readonly -mountpoint "$mnt" "$dmg" >/dev/null; then
  new="$(find "$mnt" -maxdepth 1 -name '*.app' | head -n 1)"
  [ -n "$new" ] || { [ -d "$mnt/Contents" ] && new="$mnt"; }
  if [ -n "$new" ] && mv "$app" "$app.old" && ditto "$new" "$app"; then
    rm -rf "$app.old"
  else
    [ -d "$app.old" ] && { rm -rf "$app"; mv "$app.old" "$app"; }
    hdiutil detach "$mnt" -quiet; open "$dmg"; exit 1
  fi
  hdiutil detach "$mnt" -quiet
fi
rm -f "$dmg"
open "$app"
"""


def mac_bundle() -> Path | None:
    for parent in Path(sys.executable).parents:
        if parent.suffix == ".app":
            return parent
    return None


def launch_installer(installer: Path) -> None:
    """Lance l'installation, qui continue après la fermeture de l'application, puis la relance."""
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(
            [str(installer), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
            creationflags=flags, close_fds=True,
        )
        return
    bundle = mac_bundle()
    if bundle is None:
        raise OSError("dossier de l'application introuvable")
    subprocess.Popen(
        ["/bin/sh", "-c", MAC_SCRIPT, "tms-update", str(os.getpid()), str(installer), str(bundle)],
        start_new_session=True, close_fds=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _run() -> None:
    try:
        assert data_directory is not None
        result = updates.check(version.get_version())
        if not result["available"]:
            _set("error", "Aucune mise à jour à installer.")
            return
        asset = pick_asset(result.get("assets") or [], sys.platform, platform.machine())
        if asset is None:
            _set("error", "Le fichier d'installation n'est pas encore publié pour cet ordinateur. Réessayez plus tard.")
            return
        _set("backup", "Sauvegarde de vos données…")
        try:
            backup_data(data_directory, version.get_version())
        except OSError as error:
            # L'installateur ne touche pas au dossier des données : on continue, en le disant au journal.
            print(f"Sauvegarde avant mise à jour impossible : {error}", flush=True)
        folder = data_directory / "updates"
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(exist_ok=True)
        installer = folder / Path(asset["name"]).name
        _set("download", f"Téléchargement de la version {result['version']}…", 0.0)
        download(asset, installer, lambda fraction: _set("download", f"Téléchargement de la version {result['version']}…", fraction))
        _set("install", "Installation en cours, l'application va redémarrer…")
        if quit_handler is None:
            raise OSError("application non prête")
        # L'installateur doit démarrer avant la fermeture : après, plus rien ne tourne ici.
        launch_installer(installer)
        time.sleep(1)
        quit_handler()
    except Exception as error:  # noqa: BLE001 - n'importe quel échec doit s'afficher, pas tuer le fil
        print(f"Mise à jour échouée : {error!r}", flush=True)
        _set("error", f"La mise à jour a échoué ({error}). Vos données n'ont pas été touchées. Vous pouvez réessayer ou télécharger la version à la main.")


def start() -> bool:
    """Lance la mise à jour en arrière-plan. False si une est déjà en cours."""
    with _lock:
        if _state["step"] in ("backup", "download", "install"):
            return False
        _state.update(step="backup", message="Préparation…", progress=None)
    threading.Thread(target=_run, daemon=True).start()
    return True
