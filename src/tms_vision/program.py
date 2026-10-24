"""Programme d'étirements recommandé : classement des zones par charge et
texte du motif de chaque recommandation (voir
docs/superpowers/plans/2026-10-21-poids-programme-capsules-plan.md). Module
pur, sans accès à la base.

Le classement ne dépend que de la posture : le poids saisi n'est qu'affiché
dans le motif, car il ne modifie pas les niveaux d'action par segment."""
from tms_vision.capsules import (
    MAX_PROGRAM_SIZE,
    capsule_to_dict,
    elevated_seconds_by_zone,
    rank_zones,
    recommend_capsule,
)

ZONE_LABELS = {
    "neck": "Cou",
    "trunk": "Tronc",
    "upper_arm": "Épaule / bras",
    "lower_arm": "Avant-bras / coude",
    "hand": "Main / poignet",
    "foot": "Pied / cheville",
}


def format_seconds(seconds: float) -> str:
    total = round(seconds)
    if total < 60:
        return f"{total} s"
    minutes, remainder = divmod(total, 60)
    return f"{minutes} min {remainder:02d}" if remainder else f"{minutes} min"


def format_hours(hours: float) -> str:
    total_minutes = round(hours * 60)
    whole_hours, minutes = divmod(total_minutes, 60)
    if whole_hours == 0:
        return f"{minutes} min"
    if minutes == 0:
        return f"{whole_hours} h"
    return f"{whole_hours} h {minutes:02d}"


def _format_kg(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def describe_load(load: dict | None) -> str | None:
    """Texte du poids saisi, ou None quand il n'y a pas de poids à mentionner
    (aucun poids, ou 0 kg)."""
    if load is None or load["kind"] == "none":
        return None
    if load["kind"] == "exact":
        return f"{_format_kg(load['kg'])} kg" if load["kg"] else None
    if load["kg_min"] == load["kg_max"]:
        return f"{_format_kg(load['kg_max'])} kg" if load["kg_max"] else None
    return f"{_format_kg(load['kg_min'])} à {_format_kg(load['kg_max'])} kg"


def _build_program(
    load_by_zone: dict[str, float], reason_for, position: str | None = None
) -> list[dict]:
    program = []
    for zone, load in rank_zones(load_by_zone):
        capsule = recommend_capsule(zone, position)
        if capsule is None:
            continue
        program.append({
            "rank": len(program) + 1,
            "zone": zone,
            "capsule": capsule_to_dict(capsule),
            "reason": reason_for(zone, load),
            "load": load,
            "basis": "measured",
        })
    return program


def build_analysis_program(frames: list[dict], load: dict | None) -> list[dict]:
    """Programme d'une analyse seule : charge = temps cumulé en niveau élevé
    sur l'échantillon. `frames` : lignes de storage.get_frame_segments()."""
    weight = describe_load(load)
    suffix = f" (charge manipulée : {weight})" if weight else ""

    def reason_for(zone: str, seconds: float) -> str:
        return (
            f"{ZONE_LABELS[zone]} : {format_seconds(seconds)} en posture à risque "
            f"sur l'échantillon{suffix}."
        )

    return _build_program(elevated_seconds_by_zone(frames), reason_for)


def declared_hours_by_zone(tasks: list[dict]) -> dict[str, float]:
    """Heures de tâches saisies sans vidéo qui sollicitent chaque zone, avec le nom de la tâche la
    plus longue. Sans mesure, c'est la seule information : on n'en tire aucun score de risque."""
    hours: dict[str, float] = {}
    for task in tasks:
        if task.get("analysis_id") is not None:
            continue
        for zone in task["zones"]:
            hours[zone] = hours.get(zone, 0.0) + task["activity_hours"]
    return hours


def _main_task_name(tasks: list[dict], zone: str) -> str:
    candidates = [
        task for task in tasks if task.get("analysis_id") is None and zone in task["zones"]
    ]
    return max(candidates, key=lambda task: task["activity_hours"])["name"]


def build_bilan_program(
    report: dict, position: str | None = None, tasks: list[dict] | None = None
) -> list[dict]:
    """Programme d'un bilan de poste. Les zones mesurées sur vidéo passent en premier : charge =
    heures projetées en niveau élevé sur la journée. `report` : sortie de bilan.project_bilan().
    `position` : voir bilan.preferred_position.

    Sans vidéo, rien n'est mesuré. Les places restantes (jusqu'à MAX_PROGRAM_SIZE) vont alors aux
    zones des tâches saisies (`tasks` : fiches du bilan), classées par durée de tâches qui les
    sollicitent. Ces recommandations portent `basis: "declared"` et un motif qui le dit."""
    workday = format_hours(report["workday_hours"])
    load_by_zone = {
        zone: values["projected_elevated_hours"] for zone, values in report["zones"].items()
    }

    def reason_for(zone: str, hours: float) -> str:
        return (
            f"{ZONE_LABELS[zone]} : environ {format_hours(hours)} en posture à risque "
            f"sur {workday} estimées."
        )

    program = _build_program(load_by_zone, reason_for, position)
    if tasks and len(program) < MAX_PROGRAM_SIZE:
        covered = {item["zone"] for item in program}
        declared = {
            zone: hours for zone, hours in declared_hours_by_zone(tasks).items()
            if zone not in covered
        }
        for zone, hours in rank_zones(declared, limit=MAX_PROGRAM_SIZE - len(program)):
            capsule = recommend_capsule(zone, position)
            if capsule is None:
                continue
            program.append({
                "rank": len(program) + 1,
                "zone": zone,
                "capsule": capsule_to_dict(capsule),
                "reason": (
                    f"{ZONE_LABELS[zone]} : environ {format_hours(hours)} de tâches qui la "
                    f"sollicitent, surtout « {_main_task_name(tasks, zone)} » (d'après les "
                    "tâches saisies, sans mesure vidéo)."
                ),
                "load": hours,
                "basis": "declared",
            })
    return program
