import copy
import io
import json
import subprocess
import wave
from pathlib import Path

import pytest

from tms_vision import capsule_build
from tms_vision.capsule_build import (
    BuildError,
    build_exercise,
    definition_sha256,
    ffmpeg_audio_command,
    main,
)
from tms_vision.exercises import load_catalog
from tms_vision.providers import NarrationProvider, NullNarrationProvider


def make_wav(seconds: float, rate: int = 8000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(seconds * rate))
    return buffer.getvalue()


class FakeNarration(NarrationProvider):
    name = "fake-voice"

    def __init__(self, seconds_per_instruction=1.0):
        self.calls = []
        self.seconds = seconds_per_instruction

    def synthesize(self, text, language):
        self.calls.append((text, language))
        return make_wav(self.seconds)


class FakeRunner:
    """Remplace subprocess.run : enregistre les commandes et fabrique le fichier de sortie."""

    def __init__(self, fail_node=None, fail_ffmpeg=None):
        self.calls = []
        self.fail_node = fail_node
        self.fail_ffmpeg = fail_ffmpeg

    def __call__(self, args, **kwargs):
        self.calls.append((list(args), kwargs))
        if args[0] == "node":
            if self.fail_node:
                return subprocess.CompletedProcess(args, 1, "", self.fail_node)
            Path(args[args.index("--out") + 1]).write_bytes(b"silent-video")
        elif args[0] == "ffmpeg":
            if self.fail_ffmpeg:
                return subprocess.CompletedProcess(args, 1, "", self.fail_ffmpeg)
            Path(args[-1]).write_bytes(b"video-with-audio")
        return subprocess.CompletedProcess(args, 0, "", "")

    def commands(self, program):
        return [args for args, _ in self.calls if args[0] == program]


@pytest.fixture
def exercise():
    return copy.deepcopy(load_catalog()[0])


@pytest.fixture
def out_dir(tmp_path):
    return tmp_path / "capsules"


def build(exercise, out_dir, runner, **kwargs):
    options = {
        "capsules_dir": out_dir, "runner": runner, "narration": NullNarrationProvider(),
        "base_url": "http://render.test", "fps": 5, "language": "fr",
    }
    options.update(kwargs)
    return build_exercise(exercise, **options)


def read_meta(out_dir, exercise):
    return json.loads((out_dir / f"{exercise['id']}.json").read_text("utf-8"))


# --- Rendu sans voix -------------------------------------------------------------------

def test_silent_build_renders_with_node_and_writes_the_video_and_its_metadata(exercise, out_dir):
    runner = FakeRunner()

    status = build(exercise, out_dir, runner)

    assert status == "built"
    assert (out_dir / f"{exercise['id']}.mp4").read_bytes() == b"silent-video"
    meta = read_meta(out_dir, exercise)
    assert meta["definition_sha256"] == definition_sha256(exercise)
    assert meta["fps"] == 5
    assert meta["language"] == "fr"
    assert meta["narration"] is None
    assert meta["duration_seconds"] == exercise["duration_seconds"]
    assert meta["rendered_at"].endswith("+00:00")
    assert runner.commands("ffmpeg") == []


def test_render_command_gets_the_definition_fps_and_server(exercise, out_dir):
    runner = FakeRunner()
    seen_definition = {}

    def run(args, **kwargs):
        if args[0] == "node":
            seen_definition.update(json.loads(Path(args[args.index("--definition") + 1]).read_text("utf-8")))
        return runner(args, **kwargs)

    build(exercise, out_dir, run)

    node_call = runner.commands("node")[0]
    assert node_call[1].endswith("render-exercise.mjs")
    assert node_call[node_call.index("--fps") + 1] == "5"
    assert node_call[node_call.index("--base-url") + 1] == "http://render.test"
    assert seen_definition == exercise


def test_gpu_rendering_is_opt_in_and_does_not_make_a_video_stale(exercise, out_dir):
    default_runner, gpu_runner = FakeRunner(), FakeRunner()

    build(exercise, out_dir, default_runner)
    status = build(exercise, out_dir, gpu_runner, gpu=True, force=True)
    skipped = build(exercise, out_dir, FakeRunner(), gpu=True)

    assert "--gpu" not in default_runner.commands("node")[0]
    assert "--gpu" in gpu_runner.commands("node")[0]
    assert status == "built"
    assert skipped == "skipped"


def test_cli_passes_the_gpu_flag_to_the_renderer(monkeypatch, tmp_path):
    runner = FakeRunner()
    _patch_cli(monkeypatch, tmp_path, runner)

    assert main(["--id", load_catalog()[0]["id"], "--gpu"]) == 0
    assert "--gpu" in runner.commands("node")[0]


def test_a_build_with_no_narration_provider_never_calls_ffmpeg_or_a_voice(exercise, out_dir):
    runner = FakeRunner()

    build(exercise, out_dir, runner)

    assert runner.commands("ffmpeg") == []


# --- Idempotence et mise à jour ---------------------------------------------------------

def test_an_up_to_date_video_is_skipped(exercise, out_dir):
    build(exercise, out_dir, FakeRunner())
    runner = FakeRunner()

    status = build(exercise, out_dir, runner)

    assert status == "skipped"
    assert runner.calls == []


def test_force_rebuilds_an_up_to_date_video(exercise, out_dir):
    build(exercise, out_dir, FakeRunner())
    runner = FakeRunner()

    assert build(exercise, out_dir, runner, force=True) == "built"
    assert len(runner.commands("node")) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"fps": 10},
        {"language": "en"},
        {"narration": FakeNarration()},
    ],
    ids=["fps", "language", "narration"],
)
def test_changing_a_render_setting_rebuilds(exercise, out_dir, change):
    build(exercise, out_dir, FakeRunner())

    assert build(exercise, out_dir, FakeRunner(), **change) == "built"


def test_changing_the_definition_rebuilds(exercise, out_dir):
    build(exercise, out_dir, FakeRunner())
    changed = copy.deepcopy(exercise)
    changed["instructions"][0]["text"] = "Une autre consigne."

    assert build(changed, out_dir, FakeRunner()) == "built"
    assert read_meta(out_dir, exercise)["definition_sha256"] == definition_sha256(changed)


def test_a_missing_video_file_is_rebuilt_even_if_the_metadata_matches(exercise, out_dir):
    build(exercise, out_dir, FakeRunner())
    (out_dir / f"{exercise['id']}.mp4").unlink()

    assert build(exercise, out_dir, FakeRunner()) == "built"


def test_the_hash_ignores_key_order_but_not_content(exercise):
    reordered = dict(reversed(list(exercise.items())))

    assert definition_sha256(reordered) == definition_sha256(exercise)
    changed = copy.deepcopy(exercise)
    changed["title"] += "!"
    assert definition_sha256(changed) != definition_sha256(exercise)


# --- Validation et échecs ---------------------------------------------------------------

def test_an_invalid_definition_fails_by_naming_the_field_and_writes_nothing(exercise, out_dir):
    exercise["zone"] = "knee"
    runner = FakeRunner()

    with pytest.raises(ValueError, match="zone"):
        build(exercise, out_dir, runner)

    assert runner.calls == []
    assert not out_dir.exists() or list(out_dir.iterdir()) == []


def test_a_render_failure_raises_with_the_error_output_and_writes_nothing(exercise, out_dir):
    with pytest.raises(BuildError, match="serveur injoignable"):
        build(exercise, out_dir, FakeRunner(fail_node="serveur injoignable"))

    assert not (out_dir / f"{exercise['id']}.mp4").exists()
    assert not (out_dir / f"{exercise['id']}.json").exists()


def test_a_failed_rebuild_keeps_the_previous_video(exercise, out_dir):
    build(exercise, out_dir, FakeRunner())
    changed = copy.deepcopy(exercise)
    changed["title"] = "Autre titre"

    with pytest.raises(BuildError):
        build(changed, out_dir, FakeRunner(fail_node="échec"))

    assert (out_dir / f"{exercise['id']}.mp4").read_bytes() == b"silent-video"
    assert read_meta(out_dir, exercise)["definition_sha256"] == definition_sha256(exercise)


# --- Voix ------------------------------------------------------------------------------

def test_narration_is_requested_once_per_instruction_in_the_requested_language(exercise, out_dir):
    voice = FakeNarration(seconds_per_instruction=0.5)

    build(exercise, out_dir, FakeRunner(), narration=voice, language="fr")

    assert [text for text, _ in voice.calls] == [i["text"] for i in exercise["instructions"]]
    assert {language for _, language in voice.calls} == {"fr"}


def test_a_narrated_build_mixes_audio_with_ffmpeg_and_records_the_provider(exercise, out_dir):
    runner = FakeRunner()

    build(exercise, out_dir, runner, narration=FakeNarration(0.5))

    ffmpeg_call = runner.commands("ffmpeg")[0]
    assert "-filter_complex" in ffmpeg_call
    assert (out_dir / f"{exercise['id']}.mp4").read_bytes() == b"video-with-audio"
    assert read_meta(out_dir, exercise)["narration"] == "fake-voice"


def test_an_audio_mixing_failure_raises_and_keeps_the_previous_state(exercise, out_dir):
    with pytest.raises(BuildError, match="mixage"):
        build(exercise, out_dir, FakeRunner(fail_ffmpeg="boom"), narration=FakeNarration(0.5))

    assert not (out_dir / f"{exercise['id']}.mp4").exists()


def test_a_provider_returning_nothing_for_every_instruction_leaves_a_silent_video(exercise, out_dir):
    class Silent(NarrationProvider):
        name = "silent"

        def synthesize(self, text, language):
            return None

    runner = FakeRunner()

    build(exercise, out_dir, runner, narration=Silent())

    assert runner.commands("ffmpeg") == []
    assert (out_dir / f"{exercise['id']}.mp4").read_bytes() == b"silent-video"


def test_ffmpeg_command_places_each_voice_segment_at_its_scheduled_time(tmp_path):
    segments = [(tmp_path / "a.wav", 0.5, 1.0), (tmp_path / "b.wav", 2.8, 0.5)]

    command, extra = ffmpeg_audio_command(tmp_path / "v.mp4", segments, 4.0, tmp_path / "o.mp4")

    graph = command[command.index("-filter_complex") + 1]
    # Silence de 0.5 s, voix 1, silence de 2.8 - 1.5 = 1.3 s, voix 2.
    assert "d=0.500" in graph and "d=1.300" in graph
    assert "concat=n=4:v=0:a=1[aout]" in graph
    assert extra == 0
    assert command[command.index("-c:v") + 1] == "copy"
    assert command[-1] == str(tmp_path / "o.mp4")


def test_ffmpeg_command_extends_the_video_when_the_voice_outlasts_it(tmp_path):
    segments = [(tmp_path / "a.wav", 2.8, 1.5)]  # finit à 4.3 s

    command, extra = ffmpeg_audio_command(tmp_path / "v.mp4", segments, 4.0, tmp_path / "o.mp4")

    assert extra == pytest.approx(0.3)
    assert "tpad=stop_mode=clone:stop_duration=0.300" in command[command.index("-vf") + 1]
    assert command[command.index("-c:v") + 1] == "libx264"


def test_a_long_voice_extends_the_recorded_duration(exercise, out_dir):
    # Une seule consigne très longue, dite à t=0 : plus longue que l'exercice.
    exercise["instructions"] = [{"t": 0, "text": "Très long."}]
    voice = FakeNarration(seconds_per_instruction=float(exercise["duration_seconds"]) + 5)

    build(exercise, out_dir, FakeRunner(), narration=voice)

    assert read_meta(out_dir, exercise)["duration_seconds"] == pytest.approx(exercise["duration_seconds"] + 5)


# --- Ligne de commande -----------------------------------------------------------------

def _patch_cli(monkeypatch, tmp_path, runner):
    monkeypatch.setattr(capsule_build, "CAPSULES_DIR", tmp_path / "capsules")
    monkeypatch.setattr(capsule_build.subprocess, "run", runner)
    monkeypatch.setattr(capsule_build, "get_narration_provider", lambda: NullNarrationProvider())


def test_cli_requires_either_ids_or_all(monkeypatch, tmp_path, capsys):
    _patch_cli(monkeypatch, tmp_path, FakeRunner())

    assert main([]) == 2
    assert main(["--all", "--id", "x"]) == 2


def test_cli_rejects_an_unknown_exercise_id(monkeypatch, tmp_path, capsys):
    _patch_cli(monkeypatch, tmp_path, FakeRunner())

    assert main(["--id", "inconnu"]) == 2
    assert "inconnu" in capsys.readouterr().err


def test_cli_builds_every_exercise_and_reports_skips(monkeypatch, tmp_path, capsys):
    runner = FakeRunner()
    _patch_cli(monkeypatch, tmp_path, runner)

    assert main(["--all", "--fps", "5"]) == 0
    first = capsys.readouterr().out
    assert main(["--all", "--fps", "5"]) == 0
    second = capsys.readouterr().out

    catalog = load_catalog()
    assert len(runner.commands("node")) == len(catalog)
    for exercise in catalog:
        assert f"rendu {exercise['id']}" in first
        assert f"ignoré {exercise['id']}" in second


def test_cli_keeps_going_after_a_failure_and_exits_non_zero(monkeypatch, tmp_path, capsys):
    catalog = load_catalog()
    failing_id = catalog[1]["id"]

    def runner(args, **kwargs):
        if args[0] == "node":
            definition = json.loads(Path(args[args.index("--definition") + 1]).read_text("utf-8"))
            if definition["id"] == failing_id:
                return subprocess.CompletedProcess(args, 1, "", "rendu impossible")
            Path(args[args.index("--out") + 1]).write_bytes(b"v")
        return subprocess.CompletedProcess(args, 0, "", "")

    _patch_cli(monkeypatch, tmp_path, runner)

    code = main(["--all"])

    captured = capsys.readouterr()
    assert code == 1
    assert f"ÉCHEC {failing_id}" in captured.err
    built = [path.stem for path in (tmp_path / "capsules").glob("*.mp4")]
    assert sorted(built) == sorted(e["id"] for e in catalog if e["id"] != failing_id)
