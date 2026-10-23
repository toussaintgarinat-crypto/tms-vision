"""Numéro de version de l'application, lu dans le fichier VERSION à la racine du dépôt (voir
docs/VERSIONS.md). Dans l'image Docker, ce fichier est copié à côté de src/."""
from pathlib import Path

VERSION_FILE = Path(__file__).resolve().parents[2] / "VERSION"
UNKNOWN = "inconnue"


def get_version() -> str:
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip() or UNKNOWN
    except OSError:
        return UNKNOWN
