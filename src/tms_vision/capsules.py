"""Sélection de la capsule d'étirement recommandée en fonction de la zone
RULA la plus dégradée d'une analyse terminée (voir
docs/superpowers/specs/2026-09-22-capsule-zone-recommendation-design.md).
Module pur, sans dépendance à DuckDB : il calcule uniquement à partir des
lignes de frame que storage.get_frame_segments() a déjà lues."""
from dataclasses import dataclass

ZONES = ["neck", "trunk", "upper_arm", "lower_arm"]
ZONE_PRIORITY = ["trunk", "neck", "upper_arm", "lower_arm"]
ELEVATED_LEVELS = {"investigation_et_changement_bientot", "changement_immediat"}


@dataclass
class Capsule:
    zone: str
    title: str
    description: str
    video_url: str


CAPSULES: list[Capsule] = [
    Capsule(
        zone="neck",
        title="Étirements cervicaux",
        description=(
            "3 étirements pour décompresser les cervicales après une posture tête baissée "
            "prolongée."
        ),
        video_url="https://example.com/capsules/neck-stretch.mp4",
    ),
    Capsule(
        zone="trunk",
        title="Mobilisation lombaire",
        description=(
            "Exercices doux de mobilisation du bas du dos après une posture penchée en avant."
        ),
        video_url="https://example.com/capsules/trunk-mobility.mp4",
    ),
    Capsule(
        zone="upper_arm",
        title="Étirement des épaules",
        description=(
            "Étirement des épaules après un travail prolongé bras levés ou écartés du corps."
        ),
        video_url="https://example.com/capsules/shoulder-stretch.mp4",
    ),
    Capsule(
        zone="lower_arm",
        title="Étirement de l'avant-bras et du coude",
        description=(
            "Étirement de l'avant-bras après une flexion répétée ou prolongée du coude."
        ),
        video_url="https://example.com/capsules/forearm-stretch.mp4",
    ),
]


def _segment_column(zone: str) -> str:
    return f"{zone}_segment_action_level"


def compute_worst_zone(frames: list[dict]) -> str | None:
    cumulative_seconds = {zone: 0.0 for zone in ZONES}

    for index, frame in enumerate(frames):
        if index + 1 < len(frames):
            next_timestamp = frames[index + 1]["timestamp_seconds"]
        else:
            next_timestamp = None

        if next_timestamp is None:
            duration = 1.0 if len(frames) == 1 else 0.0
        else:
            duration = max(next_timestamp - frame["timestamp_seconds"], 0.0) or (
                1.0 if len(frames) == 1 else 0.0
            )

        for zone in ZONES:
            if frame[_segment_column(zone)] in ELEVATED_LEVELS:
                cumulative_seconds[zone] += duration

    best_zone = None
    best_seconds = 0.0
    for zone in ZONE_PRIORITY:
        seconds = cumulative_seconds[zone]
        if seconds > best_seconds:
            best_zone = zone
            best_seconds = seconds

    return best_zone


def recommend_capsule(zone: str | None) -> Capsule | None:
    if zone is None:
        return None
    for capsule in CAPSULES:
        if capsule.zone == zone:
            return capsule
    return None
