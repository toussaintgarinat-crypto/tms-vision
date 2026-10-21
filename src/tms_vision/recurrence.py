"""Indicateurs de récurrence des mouvements par zone anatomique, calculés à
partir des lignes de frame d'une analyse terminée (voir
docs/superpowers/specs/2026-10-21-recurrence-programme-etirements-design.md).
Module pur, sans dépendance à DuckDB : il calcule uniquement à partir des
lignes que storage.get_frame_angles() a déjà lues.

Aucun seuil n'est codé ici : ils sont lus par zone dans
recurrence_thresholds.json, à calibrer avec l'ostéopathe (voir `calibrated`)."""
import json
from pathlib import Path

from tms_vision.capsules import ELEVATED_LEVELS, ZONES, frame_durations
from tms_vision.rula.scoring import count_direction_changes, longest_static_span_seconds

THRESHOLDS_PATH = Path(__file__).with_name("recurrence_thresholds.json")
THRESHOLD_KEYS = {
    "min_prominence_deg",
    "static_variation_deg",
    "repetitive_cycles_per_minute",
    "static_seconds",
}

ZONE_ANGLE_COLUMN = {
    "neck": "neck_flexion_deg",
    "trunk": "trunk_flexion_deg",
    "upper_arm": "upper_arm_flexion_deg",
    "lower_arm": "lower_arm_angle_deg",
}


def load_thresholds(path: Path | str | None = None) -> dict:
    with open(path or THRESHOLDS_PATH) as f:
        thresholds = json.load(f)

    zones = thresholds.get("zones", {})
    for zone in ZONES:
        if zone not in zones or set(zones[zone]) != THRESHOLD_KEYS:
            raise ValueError(
                f"Seuils de récurrence invalides pour la zone '{zone}' : "
                f"clés attendues {sorted(THRESHOLD_KEYS)}."
            )
    return {"calibrated": bool(thresholds.get("calibrated", False)), "zones": zones}


def _sample_seconds(frames: list[dict]) -> float:
    if not frames:
        return 0.0
    if len(frames) == 1:
        return 1.0
    return max(frames[-1]["timestamp_seconds"] - frames[0]["timestamp_seconds"], 0.0)


def _zone_history(frames: list[dict], zone: str) -> list[tuple[float, float]]:
    column = ZONE_ANGLE_COLUMN[zone]
    return [
        (frame["timestamp_seconds"], frame[column])
        for frame in frames
        if frame["detected"] and frame[column] is not None
    ]


def _assess(cycles_per_minute: float | None, threshold: float | None) -> str | None:
    if threshold is None or cycles_per_minute is None:
        return None
    return "repetitive" if cycles_per_minute >= threshold else "not_repetitive"


def compute_recurrence(frames: list[dict], thresholds: dict) -> dict:
    sample_seconds = _sample_seconds(frames)
    durations = frame_durations(frames)
    zones = {}

    for zone in ZONES:
        zone_thresholds = thresholds["zones"][zone]
        history = _zone_history(frames, zone)

        if len(history) >= 2:
            cycles = count_direction_changes(
                history, min_prominence_deg=zone_thresholds["min_prominence_deg"]
            ) / 2.0
            longest_static = longest_static_span_seconds(
                history, variation_deg=zone_thresholds["static_variation_deg"]
            )
            history_span = history[-1][0] - history[0][0]
        else:
            cycles = 0.0
            longest_static = 0.0
            history_span = 0.0

        cycles_per_minute = cycles / (sample_seconds / 60.0) if sample_seconds > 0 else None
        mean_cycle_seconds = history_span / cycles if cycles > 0 else None
        elevated_seconds = sum(
            duration
            for frame, duration in zip(frames, durations)
            if frame[f"{zone}_segment_action_level"] in ELEVATED_LEVELS
        )

        zones[zone] = {
            "cycles": cycles,
            "cycles_per_minute": cycles_per_minute,
            "mean_cycle_seconds": mean_cycle_seconds,
            "longest_static_seconds": longest_static,
            "elevated_seconds": elevated_seconds,
            "assessment": _assess(
                cycles_per_minute, zone_thresholds["repetitive_cycles_per_minute"]
            ),
        }

    return {
        "sample_seconds": sample_seconds,
        "thresholds_calibrated": thresholds["calibrated"],
        "zones": zones,
    }
