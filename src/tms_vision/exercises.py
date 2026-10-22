"""Définitions d'exercices d'étirement : fichiers JSON versionnés dans
`exercises/`, validés ici, qui alimentent le catalogue de capsules (voir
docs/superpowers/plans/2026-10-21-generation-modules-etirement-plan.md).

Une pose donne, par os du squelette articulé de l'avatar 3D (24 os), trois angles
(`flexion`, `lateral`, `twist`, en degrés) RELATIFS à l'os parent : un os sans angle
reste aligné sur son parent. Le rendu les convertit en pose du squelette. Un exercice `source: "ai"` n'existe que dans
`exercises/drafts/` et n'entre jamais au catalogue : un humain doit le relire,
le corriger et le valider avant."""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from tms_vision.providers import ExerciseProvider, ProviderError, get_exercise_provider

EXERCISES_DIR = Path(__file__).resolve().parents[2] / "exercises"

# Les quatre zones RULA mesurées : ce sont elles que l'analyse note et que le programme d'étirements
# classe. Les régions ajoutées avec le corps complet (tête, épaule, main, hanche, cuisse, jambe,
# pied) n'ont pas de mesure ; leurs exercices existent au catalogue et se génèrent, mais aucun
# score ne les recommande encore.
ZONES = ("neck", "trunk", "upper_arm", "lower_arm", "hand", "foot")
REGIONS = ZONES + ("head", "shoulder", "hip", "thigh", "lower_leg")
_SIDED_BONES = (
    "clavicle", "upper_arm", "forearm", "hand", "fingers", "thumb", "thigh", "shin", "foot", "toes",
)
BONES = ("spine", "neck", "head") + tuple(
    f"{side}_{bone}" for bone in _SIDED_BONES for side in ("L", "R")
)
ANGLE_KEYS = ("flexion", "lateral", "twist")
STATUSES = ("draft", "validated")
SOURCES = ("human", "ai")
VIEWS = ("front", "side", "three_quarter")
# Position du corps. Facultatif : un exercice sans `position` est debout. Les angles d'un exercice
# assis s'ajoutent à la position assise (cuisses horizontales, genoux à 90°) ; un exercice allongé
# est couché sur le dos (voir exercises/README.md).
POSITIONS = ("standing", "seated", "lying")
DEFAULT_POSITION = "standing"

MIN_DURATION_SECONDS = 10
MAX_DURATION_SECONDS = 180
MAX_ANGLE_DEG = 180

REQUIRED_KEYS = (
    "id", "zone", "title", "description", "status", "source", "validated_by", "validated_on",
    "view", "target_segments", "poses", "keyframes", "instructions", "duration_seconds",
)
OPTIONAL_KEYS = ("position",)
_ID_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _fail(field: str, message: str) -> None:
    raise ValueError(f"{field} : {message}")


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_text(data: dict, field: str) -> None:
    value = data[field]
    if not isinstance(value, str) or not value.strip():
        _fail(field, "texte non vide attendu.")


def _check_choice(data: dict, field: str, choices: tuple) -> None:
    if data[field] not in choices:
        _fail(field, f"valeur '{data[field]}' inconnue (attendu : {', '.join(choices)}).")


def _check_poses(poses) -> None:
    if not isinstance(poses, dict) or not poses:
        _fail("poses", "dictionnaire non vide attendu.")
    for pose_name, pose in poses.items():
        if not isinstance(pose, dict):
            _fail(f"poses.{pose_name}", "dictionnaire d'os attendu.")
        for bone, angles in pose.items():
            if bone not in BONES:
                _fail(f"poses.{pose_name}", f"os inconnu '{bone}' (attendu : {', '.join(BONES)}).")
            if not isinstance(angles, dict):
                _fail(f"poses.{pose_name}.{bone}", "dictionnaire d'angles attendu.")
            for key, value in angles.items():
                if key not in ANGLE_KEYS:
                    _fail(f"poses.{pose_name}.{bone}", f"angle inconnu '{key}'.")
                if not _is_number(value):
                    _fail(f"poses.{pose_name}.{bone}.{key}", "nombre attendu.")
                if abs(value) > MAX_ANGLE_DEG:
                    _fail(
                        f"poses.{pose_name}.{bone}.{key}",
                        f"l'angle doit être compris entre -{MAX_ANGLE_DEG} et {MAX_ANGLE_DEG}.",
                    )


def _check_keyframes(keyframes, poses: dict, duration) -> None:
    if not isinstance(keyframes, list) or len(keyframes) < 2:
        _fail("keyframes", "au moins deux poses clés attendues.")
    previous_t = None
    for index, keyframe in enumerate(keyframes):
        if not isinstance(keyframe, dict) or set(keyframe) != {"t", "pose"}:
            _fail(f"keyframes[{index}]", "attendu : {t, pose}.")
        if not _is_number(keyframe["t"]) or keyframe["t"] < 0:
            _fail(f"keyframes[{index}]", "t doit être un nombre positif ou nul.")
        if keyframe["pose"] not in poses:
            _fail(f"keyframes[{index}]", f"pose inconnue '{keyframe['pose']}'.")
        if previous_t is not None and keyframe["t"] <= previous_t:
            _fail("keyframes", "les instants t doivent être strictement croissants.")
        previous_t = keyframe["t"]
    if keyframes[0]["t"] != 0:
        _fail("keyframes", "la première pose clé doit être à t = 0.")
    if keyframes[-1]["t"] > duration:
        _fail("keyframes", "la dernière pose clé dépasse duration_seconds.")


def _check_instructions(instructions, duration) -> None:
    if not isinstance(instructions, list) or not instructions:
        _fail("instructions", "au moins une consigne attendue.")
    previous_t = None
    for index, instruction in enumerate(instructions):
        if not isinstance(instruction, dict) or set(instruction) != {"t", "text"}:
            _fail(f"instructions[{index}]", "attendu : {t, text}.")
        if not _is_number(instruction["t"]) or instruction["t"] < 0 or instruction["t"] > duration:
            _fail(f"instructions[{index}]", "t doit être compris entre 0 et duration_seconds.")
        if not isinstance(instruction["text"], str) or not instruction["text"].strip():
            _fail(f"instructions[{index}]", "texte non vide attendu.")
        if previous_t is not None and instruction["t"] <= previous_t:
            _fail("instructions", "les instants t doivent être strictement croissants.")
        previous_t = instruction["t"]


def validate_exercise(
    data: dict, *, in_drafts: bool = False, filename_stem: str | None = None
) -> None:
    """Lève ValueError, avec un message en français nommant le champ fautif, si
    la définition est invalide. `in_drafts` : le fichier est dans
    `exercises/drafts/`. `filename_stem` : nom du fichier sans extension (l'id
    doit lui être égal)."""
    if not isinstance(data, dict):
        _fail("exercice", "objet JSON attendu.")
    for key in REQUIRED_KEYS:
        if key not in data:
            _fail(key, "champ obligatoire manquant.")
    for key in data:
        if key not in REQUIRED_KEYS and key not in OPTIONAL_KEYS:
            _fail(key, "champ inconnu (faute de frappe ?).")

    if not isinstance(data["id"], str) or not _ID_PATTERN.match(data["id"]):
        _fail("id", "minuscules, chiffres et tirets uniquement (ex. neck-lateral-stretch).")
    if filename_stem is not None and data["id"] != filename_stem:
        _fail("id", f"doit être égal au nom du fichier ('{filename_stem}').")

    _check_choice(data, "zone", REGIONS)
    _check_choice(data, "status", STATUSES)
    _check_choice(data, "source", SOURCES)
    _check_choice(data, "view", VIEWS)
    if "position" in data:
        _check_choice(data, "position", POSITIONS)
    _check_text(data, "title")
    _check_text(data, "description")

    if data["source"] == "ai" and not in_drafts:
        _fail("source", "un exercice 'ai' ne peut se trouver que dans exercises/drafts/.")

    if data["status"] == "validated":
        if not isinstance(data["validated_by"], str) or not data["validated_by"].strip():
            _fail("validated_by", "obligatoire pour un exercice validé.")
        try:
            date.fromisoformat(str(data["validated_on"]))
        except ValueError:
            _fail("validated_on", "date ISO obligatoire (AAAA-MM-JJ) pour un exercice validé.")

    segments = data["target_segments"]
    if not isinstance(segments, list) or not segments:
        _fail("target_segments", "au moins un segment attendu.")
    if len(set(segments)) != len(segments):
        _fail("target_segments", "segments en double.")
    for segment in segments:
        if segment not in REGIONS:
            _fail(
                "target_segments",
                f"segment inconnu '{segment}' (attendu : {', '.join(REGIONS)}).",
            )

    duration = data["duration_seconds"]
    if not _is_number(duration) or not MIN_DURATION_SECONDS <= duration <= MAX_DURATION_SECONDS:
        _fail(
            "duration_seconds",
            f"nombre compris entre {MIN_DURATION_SECONDS} et {MAX_DURATION_SECONDS} attendu.",
        )

    _check_poses(data["poses"])
    _check_keyframes(data["keyframes"], data["poses"], duration)
    _check_instructions(data["instructions"], duration)


def load_exercise(path: Path | str) -> dict:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{path.name} : JSON invalide ({error}).") from error
    try:
        validate_exercise(data, in_drafts=path.parent.name == "drafts", filename_stem=path.stem)
    except ValueError as error:
        raise ValueError(f"{path.name} : {error}") from error
    return data


def load_catalog(directory: Path | str | None = None) -> list[dict]:
    """Exercices du catalogue : `*.json` du dossier (pas de sous-dossier, donc
    jamais `drafts/`), triés par id. Un fichier invalide fait échouer le
    chargement en nommant le fichier."""
    base = Path(directory) if directory is not None else EXERCISES_DIR
    catalog = [load_exercise(path) for path in sorted(base.glob("*.json"))]
    return sorted(catalog, key=lambda exercise: exercise["id"])


def propose_draft(
    zone: str,
    provider: ExerciseProvider,
    constraints: dict | None = None,
    *,
    directory: Path | str | None = None,
) -> Path:
    """Demande une proposition d'exercice à un fournisseur et l'écrit comme BROUILLON dans
    `exercises/drafts/`. Quoi que dise le fournisseur, l'exercice est marqué
    `source: "ai"`, `status: "draft"`, sans validation : il n'entre jamais au catalogue
    sans qu'un humain l'ait relu et déplacé. Ne remplace jamais un fichier existant."""
    if zone not in REGIONS:
        _fail("zone", f"valeur '{zone}' inconnue (attendu : {', '.join(REGIONS)}).")

    proposal = provider.propose(zone, constraints or {})
    if not isinstance(proposal, dict):
        _fail("proposition", "le fournisseur doit renvoyer un objet JSON.")

    data = {
        **proposal, "source": "ai", "status": "draft", "validated_by": None, "validated_on": None,
    }
    try:
        validate_exercise(data, in_drafts=True)
    except ValueError as error:
        raise ValueError(f"Proposition invalide : {error}") from error
    if data["zone"] != zone:
        _fail("zone", f"la proposition concerne '{data['zone']}', pas '{zone}'.")

    base = Path(directory) if directory is not None else EXERCISES_DIR
    destination = base / "drafts" / f"{data['id']}.json"
    if destination.exists() or (base / f"{data['id']}.json").exists():
        _fail("id", f"l'exercice '{data['id']}' existe déjà, il n'est pas remplacé.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tms_vision.exercises",
        description="Outils sur les définitions d'exercices.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    propose = commands.add_parser(
        "propose", help="demander un brouillon d'exercice au fournisseur d'IA configuré"
    )
    propose.add_argument("--zone", required=True, choices=REGIONS)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_request:
        return int(exit_request.code or 0)

    try:
        path = propose_draft(args.zone, get_exercise_provider())
    except (ProviderError, ValueError) as error:
        print(f"ÉCHEC : {error}", file=sys.stderr)
        return 1
    print(f"Brouillon écrit : {path} (source ai, à relire et valider par l'ostéopathe)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
