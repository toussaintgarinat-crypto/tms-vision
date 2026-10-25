# Spécification PyInstaller de l'application de bureau (voir deploy/desktop/build.py).
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

root = Path(os.environ["TMS_ROOT"])
stage = Path(os.environ["TMS_STAGE"])
package = root / "src" / "tms_vision"
here = root / "deploy" / "desktop"

datas = [
    (str(root / "exercises"), "exercises"),
    (str(root / "metiers"), "metiers"),
    (str(root / "library"), "library"),
    (str(root / "VERSION"), "."),
    (str(package / "models"), "tms_vision/models"),
    (str(package / "extremity_thresholds.json"), "tms_vision"),
    (str(package / "recurrence_thresholds.json"), "tms_vision"),
    (str(here / "icon.png"), "assets"),
    (str(stage / "web"), "web"),
    (str(stage / "node"), "node"),
]
binaries = []
hiddenimports = collect_submodules("tms_vision") + collect_submodules("uvicorn")
for name in ("mediapipe", "imageio_ffmpeg"):
    more_datas, more_binaries, more_hidden = collect_all(name)
    datas += more_datas
    binaries += more_binaries
    hiddenimports += more_hidden

analysis = Analysis(
    [str(package / "desktop.py")],
    pathex=[str(root / "src")],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
)
archive = PYZ(analysis.pure)
executable = EXE(
    archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="TMS Vision",
    console=False,
    icon=str(here / "icon.ico"),
)
collection = COLLECT(executable, analysis.binaries, analysis.datas, name="TMS Vision")
if sys.platform == "darwin":
    app = BUNDLE(
        collection,
        name="TMS Vision.app",
        icon=str(here / "icon.icns"),
        bundle_identifier="fr.tms-vision.app",
        info_plist={
            "NSCameraUsageDescription": "TMS Vision filme le poste de travail pour l'analyse.",
            "CFBundleShortVersionString": (root / "VERSION").read_text(encoding="utf-8").strip(),
        },
    )
