"""Construit l'application de bureau (dossier « TMS Vision » dans dist/), depuis la racine du dépôt :

    pip install -r requirements.txt -r deploy/desktop/requirements.txt
    python deploy/desktop/build.py

Prérequis : Python 3.11, Node.js 20 (npm). Étapes : construction du site en mode « standalone » (le
port de l'API y est figé, voir src/tms_vision/desktop.py), rassemblement du site et du Node.js dans
build/desktop/stage, puis PyInstaller (deploy/desktop/tms-vision.spec). Les installateurs (Windows :
deploy/desktop/installer.iss, macOS : .dmg) sont fabriqués ensuite par .github/workflows/desktop.yml."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
STAGE = ROOT / "build" / "desktop" / "stage"
sys.path.insert(0, str(ROOT / "src"))

from tms_vision.desktop import API_PORT  # noqa: E402


def run(command: list[str], **kwargs) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, check=True, **kwargs)


def build_site() -> None:
    npm = shutil.which("npm")
    if npm is None:
        sys.exit("npm introuvable : installez Node.js 20.")
    env = {
        **os.environ,
        "TMS_STANDALONE": "1",
        "NEXT_TELEMETRY_DISABLED": "1",
        "NEXT_PUBLIC_API_URL": f"http://127.0.0.1:{API_PORT}",
    }
    run([npm, "ci", "--no-audit", "--no-fund"], cwd=WEB, env=env)
    run([npm, "run", "build"], cwd=WEB, env=env)


def assemble() -> None:
    shutil.rmtree(STAGE, ignore_errors=True)
    standalone = WEB / ".next" / "standalone"
    if not (standalone / "server.js").is_file():
        sys.exit(f"{standalone / 'server.js'} introuvable : le build du site a échoué ?")
    shutil.copytree(standalone, STAGE / "web")
    # Next.js ne copie ni les fichiers statiques ni public/ dans le dossier standalone.
    shutil.copytree(WEB / ".next" / "static", STAGE / "web" / ".next" / "static")
    if (WEB / "public").is_dir():
        shutil.copytree(WEB / "public", STAGE / "web" / "public")
    node = shutil.which("node")
    if node is None:
        sys.exit("node introuvable.")
    (STAGE / "node").mkdir(parents=True)
    shutil.copy2(node, STAGE / "node" / Path(node).name)


def package() -> None:
    env = {**os.environ, "TMS_STAGE": str(STAGE), "TMS_ROOT": str(ROOT)}
    run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build" / "desktop" / "pyi"),
         str(ROOT / "deploy" / "desktop" / "tms-vision.spec")],
        env=env,
    )


if __name__ == "__main__":
    build_site()
    assemble()
    package()
    print("Application construite dans", ROOT / "dist")
