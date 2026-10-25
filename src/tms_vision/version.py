"""Numéro de version de l'application, lu dans le fichier VERSION à la racine du dépôt (voir
docs/VERSIONS.md). Dans l'image Docker, ce fichier est copié à côté de src/."""
from tms_vision.paths import resource_root

VERSION_FILE = resource_root() / "VERSION"
UNKNOWN = "inconnue"


def get_version() -> str:
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip() or UNKNOWN
    except OSError:
        return UNKNOWN
