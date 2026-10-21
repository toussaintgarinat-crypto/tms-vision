"""Projection de la récurrence d'un bilan de poste sur la journée de travail
(voir docs/superpowers/specs/2026-10-21-recurrence-programme-etirements-design.md).
Chaque analyse du bilan est un échantillon représentatif d'une activité dont
l'opérateur donne la durée dans la journée ; les mesures de l'échantillon sont
extrapolées à cette durée puis additionnées. Module pur, sans dépendance à
DuckDB : il calcule à partir des sorties de recurrence.compute_recurrence."""
from tms_vision.capsules import ZONES

SHORT_SAMPLE_SECONDS = 30.0
_HOURS_TOLERANCE = 1e-9


def project_bilan(workday_hours: float, items: list[dict]) -> dict:
    if workday_hours <= 0:
        raise ValueError("La durée de journée doit être strictement positive.")
    for item in items:
        if item["activity_hours"] <= 0:
            raise ValueError("La durée d'activité doit être strictement positive.")

    documented_hours = sum(item["activity_hours"] for item in items)
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

        if included:
            for zone in ZONES:
                zone_values = recurrence["zones"][zone]
                cycles_per_minute = zone_values["cycles_per_minute"]
                if cycles_per_minute is not None:
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
            "activity_hours": item["activity_hours"],
            "representative": included,
            "included": included,
            "sample_seconds": sample_seconds,
            "warnings": warnings,
            "recurrence": recurrence,
        })

    warnings = []
    if not any(entry["included"] for entry in analyses):
        warnings.append(
            "Aucune analyse n'est confirmée représentative de son activité : "
            "aucune projection n'est calculée."
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
        "warnings": warnings,
    }
