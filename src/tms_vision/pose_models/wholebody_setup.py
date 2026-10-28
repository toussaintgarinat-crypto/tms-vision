"""Préparation et réglage du modèle whole-body depuis le site (aucune variable d'environnement).

Les paquets (rtmlib, onnxruntime) sont installés avec l'application ; ce module gère ce qui se décide
sur le site : télécharger les poids du modèle (« Préparer le modèle », environ 330 Mo en mode
précision maximale, une seule fois, en arrière-plan) et choisir la vitesse (mode). Le mode est rangé
dans data/pose_models.json (sauvegardé avec data/, ignoré par Git).

Sans paquets (application de bureau), `status()["available"]` est faux : le site l'explique.
"""
import importlib.util
import json
import os
import threading
from pathlib import Path

from tms_vision import storage

MODES = [
    {"id": "performance", "label": "Précision maximale", "hint": "Le plus précis, le plus lent (environ 0,4 s par image sans carte graphique)."},
    {"id": "balanced", "label": "Équilibré", "hint": "Plus rapide, un peu moins précis."},
    {"id": "lightweight", "label": "Rapide", "hint": "Le plus rapide, le moins précis."},
]
MODE_IDS = [mode["id"] for mode in MODES]
DEFAULT_MODE = "performance"
APPROX_DOWNLOAD_MB = 330  # mesuré en précision maximale ; indicatif pour les autres modes

_lock = threading.Lock()
_download: dict = {"state": "idle", "message": None}


def settings_path() -> Path:
    return storage.DB_PATH.parent / "pose_models.json"


def get_mode() -> str:
    """Mode choisi sur le site ; à défaut TMS_WHOLEBODY_MODE (installations existantes), puis la précision maximale."""
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("wholebody_mode") in MODE_IDS:
            return data["wholebody_mode"]
    except (OSError, ValueError):
        pass
    env = os.environ.get("TMS_WHOLEBODY_MODE", "").strip()
    return env if env in MODE_IDS else DEFAULT_MODE


def set_mode(mode: str) -> None:
    if mode not in MODE_IDS:
        raise ValueError(f"Mode inconnu : {mode!r} (attendu : {', '.join(MODE_IDS)}).")
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"wholebody_mode": mode}, ensure_ascii=False), encoding="utf-8")


def dependencies_available() -> bool:
    return all(importlib.util.find_spec(name) is not None for name in ("rtmlib", "onnxruntime"))


def weights_paths(mode: str) -> list[tuple[str, Path]]:
    """(url, fichier attendu dans le cache de rtmlib) du détecteur et du modèle de pose du mode.
    Le nom du fichier suit la règle de rtmlib : nom de l'archive jusqu'au premier point, en .onnx."""
    from urllib.parse import urlparse

    from rtmlib import Wholebody
    from rtmlib.tools.file import _get_rtmhub_dir

    cache = Path(_get_rtmhub_dir()) / "checkpoints"
    out = []
    for key in ("det", "pose"):
        url = Wholebody.MODE[mode][key]
        name = os.path.basename(urlparse(url).path).split(".")[0] + ".onnx"
        out.append((url, cache / name))
    return out


def weights_ready(mode: str | None = None) -> bool:
    if not dependencies_available():
        return False
    try:
        return all(path.is_file() and path.stat().st_size > 0 for _, path in weights_paths(mode or get_mode()))
    except Exception:  # rtmlib change de structure interne : on dit « pas prêt » plutôt que de planter
        return False


def _run_download(mode: str) -> None:
    from rtmlib.tools.file import download_checkpoint

    try:
        pairs = weights_paths(mode)
        for index, (url, _) in enumerate(pairs, start=1):
            with _lock:
                _download.update(state="running", message=f"Téléchargement {index}/{len(pairs)}…")
            download_checkpoint(url, progress=False)
        if not weights_ready(mode):
            raise RuntimeError("fichiers introuvables après le téléchargement")
        with _lock:
            _download.update(state="done", message=None)
    except Exception as error:  # réseau coupé, disque plein, serveur de poids indisponible…
        with _lock:
            _download.update(state="error", message=f"Téléchargement impossible : {error}")


def start_download(mode: str | None = None) -> bool:
    """Lance le téléchargement en arrière-plan. `False` si un téléchargement est déjà en cours."""
    mode = mode or get_mode()
    with _lock:
        if _download["state"] == "running":
            return False
        _download.update(state="running", message="Démarrage du téléchargement…")
    threading.Thread(target=_run_download, args=(mode,), daemon=True, name="wholebody-download").start()
    return True


def status() -> dict:
    mode = get_mode()
    available = dependencies_available()
    ready = weights_ready(mode)
    with _lock:
        download = dict(_download)
    if ready and download["state"] != "running":
        download = {"state": "idle", "message": None}  # prêt : un ancien état « terminé » ou « erreur » n'a plus de sens
    return {
        "available": available,
        "mode": mode,
        "modes": MODES,
        "weights_ready": ready,
        "download": download,
        "approx_download_mb": APPROX_DOWNLOAD_MB,
    }
