"""Dossier qui contient les ressources livrées avec l'application (exercises/, metiers/, library/,
VERSION). Depuis le dépôt, c'est la racine du dépôt ; dans l'application de bureau construite avec
PyInstaller, c'est le dossier où PyInstaller décompresse les fichiers (`sys._MEIPASS`)."""
import sys
from pathlib import Path


def resource_root() -> Path:
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled)
    return Path(__file__).resolve().parents[2]
