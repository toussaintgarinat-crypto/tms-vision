"""Projection de la récurrence d'un bilan de poste sur la journée de travail
(voir docs/superpowers/specs/2026-10-21-recurrence-programme-etirements-design.md).
Chaque analyse du bilan est un échantillon représentatif d'une activité dont
l'opérateur donne la durée dans la journée ; les mesures de l'échantillon sont
extrapolées à cette durée puis additionnées. Une fiche d'activité (tâche saisie
par le soignant ou le patient) ajoute une activité sans vidéo, ou complète une
vidéo du bilan : la valeur saisie l'emporte alors sur la mesure, et les deux
restent visibles dans la sortie. Module pur, sans dépendance à DuckDB : il
calcule à partir des sorties de recurrence.compute_recurrence."""
import re

from tms_vision.capsules import ZONES

SHORT_SAMPLE_SECONDS = 30.0
_HOURS_TOLERANCE = 1e-9
_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _minutes(clock: str) -> int:
    match = _TIME_PATTERN.match(clock)
    if match is None:
        raise ValueError(f"Heure invalide : « {clock} » (format attendu HH:MM).")
    return int(match.group(1)) * 60 + int(match.group(2))


def parse_slots(slots: list[dict]) -> list[tuple[int, int]]:
    """Plages [{"start": "08:00", "end": "12:00"}] -> minutes depuis minuit, triées.
    ValueError si une heure est invalide, si la fin n'est pas après le début ou
    si deux plages se chevauchent."""
    parsed = []
    for slot in slots:
        start, end = _minutes(slot["start"]), _minutes(slot["end"])
        if end <= start:
            raise ValueError(
                f"La plage {slot['start']}–{slot['end']} doit finir après son début."
            )
        parsed.append((start, end))
    parsed.sort()
    for (_, previous_end), (next_start, _) in zip(parsed, parsed[1:]):
        if next_start < previous_end:
            raise ValueError("Les plages horaires d'une même tâche se chevauchent.")
    return parsed


def slots_hours(slots: list[dict]) -> float:
    return sum(end - start for start, end in parse_slots(slots)) / 60.0


def _slots_overlap(first: list[dict], second: list[dict]) -> bool:
    return any(
        a_start < b_end and b_start < a_end
        for a_start, a_end in parse_slots(first)
        for b_start, b_end in parse_slots(second)
    )


def project_bilan(workday_hours: float, items: list[dict], tasks: list[dict] | None = None) -> dict:
    """`tasks` : fiches d'activité (storage.list_bilan_tasks). Une fiche dont
    `analysis_id` désigne une vidéo du bilan complète cette vidéo : sa durée est
    celle de la vidéo (comptée une seule fois). Les autres sont des activités
    autonomes, comptées dans la journée."""
    tasks = tasks or []
    if workday_hours <= 0:
        raise ValueError("La durée de journée doit être strictement positive.")
    for item in items:
        if item["activity_hours"] <= 0:
            raise ValueError("La durée d'activité doit être strictement positive.")
    for task in tasks:
        if task["activity_hours"] <= 0:
            raise ValueError("La durée d'activité doit être strictement positive.")

    item_ids = {item["analysis_id"] for item in items}
    linked_tasks: dict[str, list[dict]] = {}
    standalone_tasks = []
    for task in tasks:
        if task.get("analysis_id") in item_ids:
            linked_tasks.setdefault(task["analysis_id"], []).append(task)
        else:
            standalone_tasks.append(task)

    documented_hours = sum(item["activity_hours"] for item in items) + sum(
        task["activity_hours"] for task in standalone_tasks
    )
    if documented_hours > workday_hours + _HOURS_TOLERANCE:
        raise ValueError(
            f"Les activités documentées ({documented_hours} h) dépassent la journée "
            f"({workday_hours} h)."
        )

    zones = {
        zone: {"projected_cycles": 0.0, "projected_elevated_hours": 0.0} for zone in ZONES
    }
    analyses = []

    for item in items:
        recurrence = item["recurrence"]
        sample_seconds = recurrence["sample_seconds"]
        included = bool(item["representative"])
        warnings = []
        if sample_seconds < SHORT_SAMPLE_SECONDS:
            warnings.append(
                f"Échantillon trop court ({sample_seconds:.0f} s) : "
                "la projection est peu fiable."
            )

        # La valeur saisie remplace la mesure pour les zones de la fiche ; la
        # dernière fiche liée qui nomme une zone l'emporte.
        declared_by_zone: dict[str, float] = {}
        declared = []
        for task in linked_tasks.get(item["analysis_id"], []):
            task_cycles = task.get("zone_cycles") or {}
            declared_by_zone.update(task_cycles)
            declared.append({
                "task_id": task["id"], "name": task["name"], "source": task["source"],
                "zones": task["zones"], "zone_cycles": task_cycles,
                "measured_cycles_per_minute": {
                    zone: recurrence["zones"][zone]["cycles_per_minute"]
                    for zone in task["zones"]
                },
            })

        for zone, task_cpm in declared_by_zone.items():
            zones[zone]["projected_cycles"] += task_cpm * 60.0 * item["activity_hours"]

        if included:
            for zone in ZONES:
                zone_values = recurrence["zones"][zone]
                cycles_per_minute = zone_values["cycles_per_minute"]
                if cycles_per_minute is not None and zone not in declared_by_zone:
                    zones[zone]["projected_cycles"] += (
                        cycles_per_minute * 60.0 * item["activity_hours"]
                    )
                if sample_seconds > 0:
                    zones[zone]["projected_elevated_hours"] += (
                        zone_values["elevated_seconds"] / sample_seconds
                        * item["activity_hours"]
                    )

        analyses.append({
            "analysis_id": item["analysis_id"],
            "source": "measured",
            "declared": declared,
            "activity_hours": item["activity_hours"],
            "representative": included,
            "included": included,
            "sample_seconds": sample_seconds,
            "warnings": warnings,
            "recurrence": recurrence,
        })

    task_entries = []
    for task in standalone_tasks:
        task_cycles = task.get("zone_cycles") or {}
        task_warnings = []
        missing = [zone for zone in task["zones"] if zone not in task_cycles]
        if len(missing) == len(task["zones"]):
            task_warnings.append(
                "Répétitions non renseignées : aucun cycle n'est compté pour cette tâche."
            )
        elif missing:
            task_warnings.append(
                "Répétitions non renseignées pour : " + ", ".join(missing) + "."
            )
        for zone in task["zones"]:
            if zone in task_cycles:
                zones[zone]["projected_cycles"] += task_cycles[zone] * 60.0 * task["activity_hours"]
        task_warnings.append(
            "Sans vidéo : score RULA et temps en posture à risque non mesurés."
        )
        task_entries.append({
            "task_id": task["id"], "name": task["name"], "source": task["source"],
            "zones": task["zones"], "activity_hours": task["activity_hours"],
            "time_slots": task.get("time_slots"), "zone_cycles": task_cycles,
            "warnings": task_warnings,
        })

    warnings = []
    contributes = any(
        entry["zone_cycles"] for entry in task_entries
    ) or any(
        entry["declared"] for entry in analyses
    )
    if not any(entry["included"] for entry in analyses) and not contributes:
        warnings.append(
            "Aucune analyse n'est confirmée représentative de son activité : "
            "aucune projection n'est calculée."
        )

    slotted = [task for task in tasks if task.get("time_slots")]
    for index, first in enumerate(slotted):
        for second in slotted[index + 1:]:
            if _slots_overlap(first["time_slots"], second["time_slots"]):
                warnings.append(
                    f"Les plages horaires de « {first['name']} » et de « {second['name']} » "
                    "se chevauchent : vérifiez les horaires."
                )

    return {
        "workday_hours": workday_hours,
        "documented_hours": documented_hours,
        "undocumented_hours": max(workday_hours - documented_hours, 0.0),
        "thresholds_calibrated": bool(items) and all(
            item["recurrence"]["thresholds_calibrated"] for item in items
        ),
        "zones": zones,
        "analyses": analyses,
        "tasks": task_entries,
        "warnings": warnings,
    }
