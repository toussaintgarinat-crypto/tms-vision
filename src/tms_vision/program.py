"""Programme d'étirements recommandé : classement des zones par charge et
texte du motif de chaque recommandation (voir
docs/superpowers/plans/2026-10-21-poids-programme-capsules-plan.md). Module
pur, sans accès à la base.

Le classement ne dépend que de la posture : le poids saisi n'est qu'affiché
dans le motif, car il ne modifie pas les niveaux d'action par segment."""
from tms_vision.capsules import (
    CAPSULES,
    DEFAULT_PROGRAM_SIZE,
    candidate_capsules,
    capsule_to_dict,
    elevated_seconds_by_zone,
    rank_zones,
)

ZONE_LABELS = {
    "neck": "Cou",
    "trunk": "Tronc",
    "upper_arm": "Épaule / bras",
    "lower_arm": "Avant-bras / coude",
    "hand": "Main / poignet",
    "foot": "Pied / cheville",
}


# Régions du corps que travaille un exercice (target_segments des fichiers d'exercices).
SEGMENT_LABELS = {
    "neck": "cou", "head": "tête", "trunk": "tronc", "shoulder": "épaule",
    "upper_arm": "bras", "lower_arm": "avant-bras", "hand": "main / poignet", "hip": "hanche",
    "thigh": "cuisse", "lower_leg": "jambe", "foot": "pied / cheville",
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


def _task_line(task: dict, zone: str) -> str:
    """Une tâche qui sollicite la zone : durée, poste, fréquence du geste, maintien, charge."""
    parts = [format_hours(task["activity_hours"])]
    if task.get("workstation"):
        parts.append(task["workstation"].split(" (")[0].lower())
    cycles = (task.get("zone_cycles") or {}).get(zone)
    if cycles:
        parts.append(f"{cycles:g} gestes/min")
    if task.get("static_seconds"):
        parts.append(f"maintien {format_seconds(task['static_seconds'])}")
    if task.get("load_kg"):
        parts.append(f"{_format_kg(task['load_kg'])} kg")
    return f"« {task['name']} » ({', '.join(parts)})"


def _why(zone: str, capsule, tasks: list[dict] | None, rank_in_zone: int) -> list[str]:
    """Explication affichée dans la bulle ⓘ : le mouvement du poste qui sollicite la zone, puis ce
    que fait l'exercice. Une ligne par information, rien d'inventé : seulement ce qui est saisi."""
    lines = []
    related = sorted(
        (task for task in tasks or [] if zone in task["zones"]),
        key=lambda task: -task["activity_hours"],
    )
    if related:
        lines.append(
            f"Mouvements du poste qui sollicitent {ZONE_LABELS[zone].lower()} : "
            + " ; ".join(_task_line(task, zone) for task in related[:3]) + "."
        )
    else:
        lines.append(
            f"Zone : {ZONE_LABELS[zone].lower()}. Aucune tâche saisie ne précise le mouvement "
            "du poste."
        )
    targets = [SEGMENT_LABELS.get(name, name) for name in capsule.target_segments]
    if targets:
        lines.append(f"Cet exercice fait travailler : {', '.join(targets)}.")
    if rank_in_zone > 0:
        lines.append(
            "Exercice complémentaire pour la même zone, proposé parce que vous demandez plus "
            "d'exercices."
        )
    return lines


def _zone_entries(load_by_zone: dict[str, float], reason_for, basis: str) -> list[tuple]:
    return [
        (zone, load, reason_for(zone, load), basis) for zone, load in rank_zones(load_by_zone)
    ]


def _build_program(
    entries: list[tuple], position: str | None, size: int, tasks: list[dict] | None = None
) -> list[dict]:
    """`entries` : (zone, charge, motif, base) dans l'ordre de priorité. Un exercice par zone,
    puis un deuxième par zone, etc., jusqu'à `size` exercices."""
    candidates = {entry[0]: candidate_capsules(entry[0], position) for entry in entries}
    program = []
    depth = 0
    while len(program) < size and any(len(candidates[entry[0]]) > depth for entry in entries):
        for zone, load, reason, basis in entries:
            if len(program) >= size:
                break
            if len(candidates[zone]) <= depth:
                continue
            capsule = candidates[zone][depth]
            program.append({
                "rank": len(program) + 1,
                "zone": zone,
                "capsule": capsule_to_dict(capsule),
                "reason": reason,
                "load": load,
                "basis": basis,
                "why": _why(zone, capsule, tasks, depth),
            })
        depth += 1
    return program


def build_analysis_program(
    frames: list[dict], load: dict | None, size: int = DEFAULT_PROGRAM_SIZE
) -> list[dict]:
    """Programme d'une analyse seule : charge = temps cumulé en niveau élevé
    sur l'échantillon. `frames` : lignes de storage.get_frame_segments()."""
    weight = describe_load(load)
    suffix = f" (charge manipulée : {weight})" if weight else ""

    def reason_for(zone: str, seconds: float) -> str:
        return (
            f"{ZONE_LABELS[zone]} : {format_seconds(seconds)} en posture à risque "
            f"sur l'échantillon{suffix}."
        )

    entries = _zone_entries(elevated_seconds_by_zone(frames), reason_for, "measured")
    return _build_program(entries, None, size)


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
    report: dict, position: str | None = None, tasks: list[dict] | None = None,
    size: int = DEFAULT_PROGRAM_SIZE,
) -> list[dict]:
    """Programme d'un bilan de poste, de `size` exercices. Les zones mesurées sur vidéo passent en
    premier : charge = heures projetées en niveau élevé sur la journée. `report` : sortie de
    bilan.project_bilan(). `position` : voir bilan.preferred_position.

    Sans vidéo, rien n'est mesuré. Les places restantes vont alors aux zones des tâches saisies
    (`tasks` : fiches du bilan), classées par durée de tâches qui les sollicitent. Ces
    recommandations portent `basis: "declared"` et un motif qui le dit."""
    workday = format_hours(report["workday_hours"])
    load_by_zone = {
        zone: values["projected_elevated_hours"] for zone, values in report["zones"].items()
    }

    def reason_for(zone: str, hours: float) -> str:
        return (
            f"{ZONE_LABELS[zone]} : environ {format_hours(hours)} en posture à risque "
            f"sur {workday} estimées."
        )

    entries = _zone_entries(load_by_zone, reason_for, "measured")
    if tasks:
        covered = {entry[0] for entry in entries}
        declared = {
            zone: hours for zone, hours in declared_hours_by_zone(tasks).items()
            if zone not in covered
        }

        def declared_reason(zone: str, hours: float) -> str:
            return (
                f"{ZONE_LABELS[zone]} : environ {format_hours(hours)} de tâches qui la "
                f"sollicitent, surtout « {_main_task_name(tasks, zone)} » (d'après les "
                "tâches saisies, sans mesure vidéo)."
            )

        entries += _zone_entries(declared, declared_reason, "declared")
    return _build_program(entries, position, size, tasks)


def select_program(
    exercise_ids: list[str], full_program: list[dict], tasks: list[dict] | None = None
) -> list[dict]:
    """Programme choisi par le praticien : ses exercices, dans son ordre. `full_program` : le
    programme automatique le plus large (build_bilan_program avec un grand `size`) ; un exercice
    qui n'y figure pas est ajouté à la main (`basis: "manual"`, sans score). Les identifiants
    inconnus sont ignorés."""
    by_id = {item["capsule"]["id"]: item for item in full_program}
    catalog = {capsule.id: capsule for capsule in CAPSULES}
    program = []
    for exercise_id in dict.fromkeys(exercise_ids):
        if exercise_id in by_id:
            item = by_id[exercise_id]
        elif exercise_id in catalog:
            capsule = catalog[exercise_id]
            item = {
                "zone": capsule.zone,
                "capsule": capsule_to_dict(capsule),
                "reason": "Exercice ajouté par le praticien.",
                "load": 0.0,
                "basis": "manual",
                "why": (
                    _why(capsule.zone, capsule, tasks, 0)
                    if capsule.zone in ZONE_LABELS
                    else [
                        "Exercice ajouté par le praticien.",
                        "Cet exercice fait travailler : "
                        + ", ".join(SEGMENT_LABELS.get(n, n) for n in capsule.target_segments) + ".",
                    ]
                ),
            }
        else:
            continue
        program.append({**item, "rank": len(program) + 1})
    return program
