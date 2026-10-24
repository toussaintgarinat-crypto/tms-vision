"""Bibliothèque de métiers : modèles de bilan (fiches d'activité types) qui servent de point de
départ. Fichiers JSON versionnés dans `metiers/`, validés ici ; les modèles créés par le praticien
sont stockés en base (voir storage.py) et suivent le même format.

Un modèle ne contient pas de score : les scores viennent des vidéos analysées. Il décrit
seulement les tâches habituelles du poste (zones, durées, fréquences), à ajuster pour chaque
personne. Un modèle écrit par l'IA (`source: "ai"`) reste en brouillon tant qu'un professionnel de
santé ne l'a pas relu et validé."""
import json
import re
from pathlib import Path

METIERS_DIR = Path(__file__).resolve().parents[2] / "metiers"

ZONES = ("neck", "trunk", "upper_arm", "lower_arm", "hand", "foot")
STATUSES = ("draft", "validated")
SOURCES = ("human", "ai")
DOMAINS = (
    "terrain-btp", "industrie-logistique", "alimentaire-commerce", "sante-soins",
    "tertiaire-autres",
)
_ID_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_WORKDAY_HOURS = 24

LIBRARY_KEYS = (
    "id", "title", "description", "domain", "status", "source", "validated_by", "validated_on",
    "workday_hours", "tasks",
)
_TASK_NUMBERS = (
    "activity_hours", "cycles_per_minute", "cycle_seconds", "static_seconds", "load_kg",
    "days_per_week",
)
_TASK_TEXTS = ("workstation", "breaks", "notes")
_TASK_KEYS = ("name", "zones", "zone_cycles") + _TASK_NUMBERS + _TASK_TEXTS


def _fail(field: str, message: str) -> None:
    raise ValueError(f"{field} : {message}")


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_task(task: object, field: str = "tâche") -> dict:
    """Valide une fiche type et renvoie sa forme normalisée (clés inconnues refusées)."""
    if not isinstance(task, dict):
        _fail(field, "doit être un objet")
    unknown = sorted(set(task) - set(_TASK_KEYS))
    if unknown:
        _fail(field, f"champs inconnus : {', '.join(unknown)}")
    name = task.get("name")
    if not isinstance(name, str) or not name.strip():
        _fail(field, "le nom est obligatoire")
    zones = task.get("zones")
    if not isinstance(zones, list) or not zones or any(zone not in ZONES for zone in zones):
        _fail(field, f"zones : une ou plusieurs valeurs parmi {', '.join(ZONES)}")
    hours = task.get("activity_hours")
    if not _is_number(hours) or not 0 < hours <= MAX_WORKDAY_HOURS:
        _fail(field, "activity_hours doit être un nombre entre 0 et 24")
    clean = {"name": name.strip(), "zones": list(dict.fromkeys(zones)), "activity_hours": hours}
    for key in _TASK_NUMBERS[1:]:
        value = task.get(key)
        if value is None:
            continue
        if not _is_number(value) or value < 0 or (key == "days_per_week" and not 0 < value <= 7):
            _fail(field, f"{key} doit être un nombre positif")
        clean[key] = value
    zone_cycles = task.get("zone_cycles")
    if zone_cycles is not None:
        if (
            not isinstance(zone_cycles, dict)
            or any(zone not in clean["zones"] for zone in zone_cycles)
            or any(not _is_number(value) or value < 0 for value in zone_cycles.values())
        ):
            _fail(field, "zone_cycles : une fréquence positive par zone cochée")
        clean["zone_cycles"] = dict(zone_cycles)
    for key in _TASK_TEXTS:
        value = task.get(key)
        if value is None:
            continue
        if not isinstance(value, str):
            _fail(field, f"{key} doit être un texte")
        if value.strip():
            clean[key] = value.strip()
    return clean


def validate_model(model: object) -> dict:
    """Valide un modèle de métier de la bibliothèque. ValueError sinon."""
    if not isinstance(model, dict):
        raise ValueError("le modèle doit être un objet JSON")
    missing = [key for key in LIBRARY_KEYS if key not in model]
    if missing:
        raise ValueError(f"champs manquants : {', '.join(missing)}")
    unknown = sorted(set(model) - set(LIBRARY_KEYS))
    if unknown:
        raise ValueError(f"champs inconnus : {', '.join(unknown)}")
    if not isinstance(model["id"], str) or not _ID_PATTERN.match(model["id"]):
        _fail("id", "minuscules, chiffres et tirets uniquement")
    for key in ("title", "description"):
        if not isinstance(model[key], str) or not model[key].strip():
            _fail(key, "texte obligatoire")
    if model["domain"] not in DOMAINS:
        _fail("domain", f"doit valoir l'un de : {', '.join(DOMAINS)}")
    if model["status"] not in STATUSES:
        _fail("status", f"doit valoir {' ou '.join(STATUSES)}")
    if model["source"] not in SOURCES:
        _fail("source", f"doit valoir {' ou '.join(SOURCES)}")
    if model["status"] == "validated" and not (model["validated_by"] and model["validated_on"]):
        _fail("status", "un modèle validé indique validated_by et validated_on")
    workday = model["workday_hours"]
    if not _is_number(workday) or not 0 < workday <= MAX_WORKDAY_HOURS:
        _fail("workday_hours", "doit être un nombre entre 0 et 24")
    if not isinstance(model["tasks"], list) or not model["tasks"]:
        _fail("tasks", "au moins une fiche d'activité")
    tasks = [validate_task(task, f"tasks[{i}]") for i, task in enumerate(model["tasks"])]
    total = sum(task["activity_hours"] for task in tasks)
    if total > workday + 1e-9:
        _fail("tasks", f"{total} h de tâches dépassent la journée de {workday} h")
    return {**model, "tasks": tasks}


def load_library(directory: Path | None = None) -> list[dict]:
    """Charge et valide tous les métiers du dossier, triés par titre. Un fichier invalide fait
    échouer le chargement (message avec le nom du fichier) : un modèle faux ne doit pas passer."""
    directory = directory or METIERS_DIR
    models = []
    for path in sorted(directory.glob("*.json")):
        try:
            model = validate_model(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, json.JSONDecodeError) as error:
            raise ValueError(f"{path.name} : {error}") from error
        if model["id"] != path.stem:
            raise ValueError(f"{path.name} : l'id doit être le nom du fichier ({path.stem})")
        models.append(model)
    return sorted(models, key=lambda model: model["title"].casefold())


def task_to_stored(task: dict) -> dict:
    """Fiche type → champs stockés d'une fiche de bilan (voir storage._TASK_FIELDS).
    `cycles_per_minute` s'applique à toutes les zones cochées, `zone_cycles` précise zone par zone."""
    cycles = task.get("cycles_per_minute")
    zone_cycles = {zone: cycles for zone in task["zones"]} if cycles is not None else {}
    zone_cycles.update(task.get("zone_cycles", {}))
    return {
        "name": task["name"], "zones": task["zones"], "activity_hours": task["activity_hours"],
        "time_slots": None, "days_per_week": task.get("days_per_week"),
        "zone_cycles": zone_cycles,
        "cycle_seconds": task.get("cycle_seconds"), "static_seconds": task.get("static_seconds"),
        "load_kg": task.get("load_kg"), "analysis_id": None, "source": "practitioner",
        "notes": task.get("notes"), "workstation": task.get("workstation"),
        "breaks": task.get("breaks"),
    }
