"""L'application de bureau est construite en Python 3.11 (.python-version, workflow de publication).
Une syntaxe acceptée seulement à partir de 3.12 (ex. un antislash dans une expression d'f-string) ne se
compile pas en 3.11 : PyInstaller ignore alors le module en silence et l'application plante au démarrage
(« No module named tms_vision.mailer », versions 2.0.0 à 2.2.0). Ce test compile tout le paquet en 3.11."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SOURCES = Path(__file__).resolve().parents[1] / "src" / "tms_vision"


def _python_311() -> str | None:
    if sys.version_info[:2] == (3, 11):
        return sys.executable
    return shutil.which("python3.11")


def test_the_whole_package_compiles_with_python_3_11():
    python = _python_311()
    if python is None:
        pytest.skip("Python 3.11 introuvable : le contrôle tourne à la construction de l'application")
    result = subprocess.run(
        [python, "-m", "compileall", "-q", "-x", r"__pycache__", str(SOURCES)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
