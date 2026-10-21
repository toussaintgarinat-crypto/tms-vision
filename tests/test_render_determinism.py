"""Rendu des vidéos d'exercice (web/scripts/render-exercise.mjs).

Ces tests pilotent le vrai rendu (Node, Chromium sans écran, ffmpeg) et ne tournent
que si l'environnement le permet : `node`, `ffmpeg`, les dépendances de web/
(`npm install`), un serveur Next.js joignable (TMS_RENDER_BASE_URL, par défaut
http://localhost:3000, lancé avec `npm run dev` dans web/) et Chromium (variable
CHROMIUM_PATH, ou installé pour Playwright). Sinon ils sont ignorés."""
import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = REPO_ROOT / "web"
SCRIPT = WEB_DIR / "scripts" / "render-exercise.mjs"
BASE_URL = os.environ.get("TMS_RENDER_BASE_URL", "http://localhost:3000")

FPS = 5
DURATION_SECONDS = 3


def _server_reachable() -> bool:
    try:
        with urllib.request.urlopen(f"{BASE_URL}/render/ping", timeout=3) as response:
            return response.status == 200
    except Exception:
        return False


def _run(args, **kwargs):
    return subprocess.run(
        ["node", str(SCRIPT), *args], cwd=WEB_DIR, capture_output=True, text=True, **kwargs
    )


needs_node_and_deps = pytest.mark.skipif(
    shutil.which("node") is None or not (WEB_DIR / "node_modules" / "playwright-core").is_dir(),
    reason="node ou les dépendances de web/ (npm install) sont absents",
)
needs_rendering = pytest.mark.skipif(
    shutil.which("node") is None
    or shutil.which("ffmpeg") is None
    or shutil.which("ffprobe") is None
    or not (WEB_DIR / "node_modules" / "playwright-core").is_dir()
    or not _server_reachable(),
    reason="rendu impossible : node, ffmpeg, dépendances de web/ ou serveur Next.js absents",
)


@pytest.fixture
def short_exercise(tmp_path):
    definition = json.loads((REPO_ROOT / "exercises" / "neck-lateral-stretch.json").read_text("utf-8"))
    definition["duration_seconds"] = DURATION_SECONDS
    definition["keyframes"] = [
        {"t": 0, "pose": "neutral"}, {"t": 1.5, "pose": "tilt_right"}, {"t": 3, "pose": "neutral"},
    ]
    definition["instructions"] = [{"t": 0, "text": "Court exercice de test."}]
    path = tmp_path / "short.json"
    path.write_text(json.dumps(definition, ensure_ascii=False), encoding="utf-8")
    return path


def _render(definition: Path, out: Path):
    result = _run(
        ["--definition", str(definition), "--out", str(out), "--fps", str(FPS), "--base-url", BASE_URL]
    )
    if result.returncode == 3:
        pytest.skip(f"Chromium ou ffmpeg introuvable : {result.stderr.strip()}")
    assert result.returncode == 0, result.stderr
    assert out.exists()


def _frame_hashes(video: Path) -> list[str]:
    output = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video), "-f", "framemd5", "-"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [line for line in output.splitlines() if line and not line.startswith("#")]


@needs_rendering
def test_rendered_video_has_the_expected_format_and_duration(short_exercise, tmp_path):
    out = tmp_path / "out.mp4"
    _render(short_exercise, out)

    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=codec_name,width,height,r_frame_rate,nb_frames,pix_fmt,duration",
         "-of", "json", str(out)],
        capture_output=True, text=True, check=True,
    ).stdout)["streams"][0]

    assert probe["codec_name"] == "h264"
    assert probe["pix_fmt"] == "yuv420p"
    assert (probe["width"], probe["height"]) == (640, 640)
    assert probe["r_frame_rate"] == f"{FPS}/1"
    assert int(probe["nb_frames"]) == DURATION_SECONDS * FPS
    assert float(probe["duration"]) == pytest.approx(DURATION_SECONDS, abs=1 / FPS)


@needs_rendering
def test_two_renders_of_the_same_exercise_decode_to_identical_frames(short_exercise, tmp_path):
    first, second = tmp_path / "first.mp4", tmp_path / "second.mp4"
    _render(short_exercise, first)
    _render(short_exercise, second)

    hashes = _frame_hashes(first)
    assert len(hashes) == DURATION_SECONDS * FPS
    assert hashes == _frame_hashes(second)


@needs_rendering
def test_the_pose_actually_changes_between_frames(short_exercise, tmp_path):
    out = tmp_path / "out.mp4"
    _render(short_exercise, out)

    hashes = _frame_hashes(out)

    # Début neutre, milieu incliné, fin neutre : les images du milieu diffèrent du début.
    assert hashes[len(hashes) // 2] != hashes[0]
    assert len(set(hashes)) > 3


@needs_node_and_deps
def test_script_exits_with_usage_code_on_missing_or_unknown_arguments():
    assert _run([]).returncode == 2
    assert _run(["--definition", "x.json"]).returncode == 2
    assert _run(["--definition", "x.json", "--out", "y.mp4", "--bogus"]).returncode == 2
    assert _run(["--definition", "x.json", "--out", "y.mp4", "--fps", "0"]).returncode == 2


@needs_node_and_deps
def test_script_reports_an_unreachable_server_with_its_own_exit_code(short_exercise, tmp_path):
    result = _run(
        ["--definition", str(short_exercise), "--out", str(tmp_path / "o.mp4"),
         "--base-url", "http://127.0.0.1:9"],
    )

    assert result.returncode == 4
    assert "injoignable" in result.stderr


@needs_node_and_deps
def test_script_fails_fast_when_ffmpeg_is_not_installed(short_exercise, tmp_path):
    # PATH réduit au dossier de node : ffmpeg n'y est pas (sauf installation à côté de node).
    node_dir = Path(shutil.which("node")).parent
    if (node_dir / "ffmpeg").exists():
        pytest.skip("ffmpeg est installé à côté de node : impossible de le masquer")

    result = subprocess.run(
        [shutil.which("node"), str(SCRIPT), "--definition", str(short_exercise),
         "--out", str(tmp_path / "o.mp4"), "--base-url", BASE_URL],
        cwd=WEB_DIR, capture_output=True, text=True, env={**os.environ, "PATH": str(node_dir)},
        # Un blocage (attente infinie d'un ffmpeg absent) doit faire échouer le test, pas le figer.
        timeout=60,
    )

    assert result.returncode == 3
    assert "ffmpeg" in result.stderr
