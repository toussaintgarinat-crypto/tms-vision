"""Génération des vidéos d'exercices d'étirement (voir
docs/superpowers/plans/2026-10-21-generation-modules-etirement-plan.md).

Pour chaque exercice du catalogue : valide la définition, appelle l'éventuelle voix
(fournisseur optionnel, voir providers.py), fait rendre la vidéo par le script Node
(avatar 3D animé, Chromium sans écran), mixe l'audio avec ffmpeg et écrit
`data/capsules/<id>.mp4` avec ses métadonnées `<id>.json`. Une vidéo à jour (même
définition, même cadence, même langue, même voix) n'est pas refaite.

    python -m tms_vision.capsule_build --all
    python -m tms_vision.capsule_build --id neck-lateral-stretch --force

Prérequis : serveur Next.js lancé (`npm run dev` dans web/), `ffmpeg`, `node`, Chromium
pour Playwright (voir web/scripts/render-exercise.mjs)."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from tms_vision.exercises import load_catalog, validate_exercise
from tms_vision.providers import (
    NullNarrationProvider,
    ProviderError,
    get_narration_provider,
    schedule_narration,
    wav_duration_seconds,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = REPO_ROOT / "web"
RENDER_SCRIPT = WEB_DIR / "scripts" / "render-exercise.mjs"
CAPSULES_DIR = Path("data/capsules")
DEFAULT_FPS = 15
DEFAULT_LANGUAGE = "fr"
AUDIO_SAMPLE_RATE = 44100


class BuildError(RuntimeError):
    """Échec du rendu ou du mixage d'une vidéo."""


def definition_sha256(exercise: dict) -> str:
    canonical = json.dumps(exercise, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def video_path(exercise_id: str, capsules_dir: Path | None = None) -> Path:
    return (capsules_dir or CAPSULES_DIR) / f"{exercise_id}.mp4"


def _meta_path(exercise_id: str, capsules_dir: Path) -> Path:
    return capsules_dir / f"{exercise_id}.json"


def _read_meta(exercise_id: str, capsules_dir: Path) -> dict | None:
    try:
        return json.loads(_meta_path(exercise_id, capsules_dir).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _is_up_to_date(exercise: dict, capsules_dir: Path, expected: dict) -> bool:
    meta = _read_meta(exercise["id"], capsules_dir)
    if meta is None or not video_path(exercise["id"], capsules_dir).exists():
        return False
    return all(meta.get(key) == value for key, value in expected.items())


def ffmpeg_audio_command(
    video: Path, segments: list[tuple[Path, float, float]], video_duration: float, out: Path
) -> tuple[list[str], float]:
    """Commande ffmpeg qui ajoute une piste de voix à la vidéo. `segments` : triplets
    (fichier WAV, instant de départ, durée) triés par départ et sans chevauchement (voir
    providers.schedule_narration). La piste est faite de silences et de voix mis bout à
    bout. Si la voix finit après la vidéo, la dernière image est prolongée (la vidéo est
    alors réencodée). Retourne (arguments, secondes ajoutées à la vidéo)."""
    command = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video)]
    for wav, _, _ in segments:
        command += ["-i", str(wav)]

    parts, labels, cursor = [], [], 0.0
    for n, (_, start, duration) in enumerate(segments):
        gap = start - cursor
        if gap > 0.0005:
            parts.append(f"anullsrc=r={AUDIO_SAMPLE_RATE}:cl=mono:d={gap:.3f}[s{n}]")
            labels.append(f"[s{n}]")
        parts.append(
            f"[{n + 1}:a]aresample={AUDIO_SAMPLE_RATE},"
            f"aformat=sample_fmts=fltp:channel_layouts=mono[w{n}]"
        )
        labels.append(f"[w{n}]")
        cursor = start + duration
    parts.append(f"{''.join(labels)}concat=n={len(labels)}:v=0:a=1[aout]")
    command += ["-filter_complex", ";".join(parts), "-map", "0:v", "-map", "[aout]"]

    extra = max(0.0, cursor - video_duration)
    if extra > 0:
        command += [
            "-vf", f"tpad=stop_mode=clone:stop_duration={extra:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-threads", "1",
        ]
    else:
        command += ["-c:v", "copy"]
    command += ["-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)]
    return command, extra


def _install(source: Path, destination: Path) -> None:
    """Copie atomique : on écrit à côté puis on remplace, pour ne jamais laisser une
    vidéo à moitié écrite ni perdre l'ancienne si la copie échoue."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(destination.name + ".tmp")
    shutil.copyfile(source, staging)
    os.replace(staging, destination)


def _check(result, what: str) -> None:
    if result.returncode != 0:
        details = (result.stderr or "").strip()
        raise BuildError(f"{what} (code {result.returncode}) : {details}")


def build_exercise(
    exercise: dict,
    *,
    capsules_dir: Path | None = None,
    force: bool = False,
    language: str = DEFAULT_LANGUAGE,
    fps: int = DEFAULT_FPS,
    base_url: str | None = None,
    narration=None,
    runner=None,
    gpu: bool = False,
) -> str:
    """Génère la vidéo d'un exercice. Retourne "built" ou "skipped" (déjà à jour).
    ValueError si la définition est invalide, BuildError si le rendu ou le mixage échoue,
    ProviderError si la voix échoue ; dans tous les cas la vidéo précédente est conservée.
    `gpu` : rendre avec le processeur graphique de la machine (beaucoup plus rapide, mais non
    reproductible d'une machine à l'autre) ; ne compte pas dans le test « à jour »."""
    validate_exercise(exercise)
    capsules_dir = capsules_dir or CAPSULES_DIR
    runner = runner or subprocess.run
    base_url = base_url or os.environ.get("TMS_RENDER_BASE_URL", "http://localhost:3000")
    narration = narration if narration is not None else get_narration_provider()
    narration_name = None if isinstance(narration, NullNarrationProvider) else narration.name

    digest = definition_sha256(exercise)
    expected = {
        "definition_sha256": digest, "fps": fps, "language": language, "narration": narration_name,
    }
    if not force and _is_up_to_date(exercise, capsules_dir, expected):
        return "skipped"

    instructions = exercise["instructions"]
    voices = []  # (instruction, octets WAV, durée)
    if narration_name is not None:
        for instruction in instructions:
            audio = narration.synthesize(instruction["text"], language)
            if audio is not None:
                voices.append((instruction, audio, wav_duration_seconds(audio)))

    with tempfile.TemporaryDirectory() as scratch:
        scratch = Path(scratch)
        definition_file = scratch / "definition.json"
        definition_file.write_text(json.dumps(exercise, ensure_ascii=False), encoding="utf-8")
        silent_video = scratch / "silent.mp4"

        render_command = [
            "node", str(RENDER_SCRIPT), "--definition", str(definition_file),
            "--out", str(silent_video), "--fps", str(fps), "--base-url", base_url,
        ]
        if gpu:
            render_command.append("--gpu")
        render = runner(render_command, cwd=WEB_DIR, capture_output=True, text=True)
        _check(render, "Rendu échoué")

        final_video, duration = silent_video, float(exercise["duration_seconds"])
        if voices:
            schedule = schedule_narration([v[0] for v in voices], [v[2] for v in voices])
            segments = []
            for start, index in schedule:
                wav_file = scratch / f"voice-{index}.wav"
                wav_file.write_bytes(voices[index][1])
                segments.append((wav_file, start, voices[index][2]))
            final_video = scratch / "final.mp4"
            command, extra = ffmpeg_audio_command(silent_video, segments, duration, final_video)
            _check(runner(command, capture_output=True, text=True), "Échec du mixage audio")
            duration += extra

        _install(final_video, video_path(exercise["id"], capsules_dir))

    meta = {
        **expected,
        "duration_seconds": duration,
        "rendered_at": datetime.now(timezone.utc).isoformat(),
    }
    meta_file = _meta_path(exercise["id"], capsules_dir)
    staging = meta_file.with_name(meta_file.name + ".tmp")
    staging.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(staging, meta_file)
    return "built"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tms_vision.capsule_build",
        description="Génère les vidéos des exercices d'étirement.",
    )
    parser.add_argument("--id", action="append", default=[], help="exercice à générer (répétable)")
    parser.add_argument("--all", action="store_true", help="générer tous les exercices du catalogue")
    parser.add_argument("--force", action="store_true", help="refaire même si la vidéo est à jour")
    parser.add_argument("--language", default=DEFAULT_LANGUAGE)
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS)
    parser.add_argument("--base-url", default=None, help="serveur Next.js (défaut : TMS_RENDER_BASE_URL)")
    parser.add_argument(
        "--gpu", action="store_true",
        help="rendu avec le GPU de la machine (rapide, non reproductible d'une machine à l'autre)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exit_request:
        return int(exit_request.code or 0)

    if bool(args.id) == args.all:
        print("Indiquez soit --all, soit un ou plusieurs --id (pas les deux).", file=sys.stderr)
        return 2

    catalog = {exercise["id"]: exercise for exercise in load_catalog()}
    unknown = [exercise_id for exercise_id in args.id if exercise_id not in catalog]
    if unknown:
        print(f"Exercice(s) inconnu(s) : {', '.join(unknown)}", file=sys.stderr)
        return 2

    try:
        narration = get_narration_provider()
    except ProviderError as error:
        print(f"ÉCHEC configuration : {error}", file=sys.stderr)
        return 1

    selected = list(catalog.values()) if args.all else [catalog[i] for i in args.id]
    failures = 0
    for exercise in selected:
        started = time.monotonic()
        try:
            status = build_exercise(
                exercise, force=args.force, language=args.language, fps=args.fps,
                base_url=args.base_url, narration=narration, gpu=args.gpu,
            )
        except (BuildError, ProviderError, ValueError) as error:
            failures += 1
            print(f"ÉCHEC {exercise['id']} : {error}", file=sys.stderr)
            continue
        if status == "skipped":
            print(f"ignoré {exercise['id']} (déjà à jour)")
        else:
            print(f"rendu {exercise['id']} en {time.monotonic() - started:.0f} s")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
