"""Sélection de la capsule d'étirement recommandée en fonction de la zone
RULA la plus dégradée d'une analyse terminée (voir
docs/superpowers/specs/2026-09-22-capsule-zone-recommendation-design.md).
Module pur, sans dépendance à DuckDB : il calcule uniquement à partir des
lignes de frame que storage.get_frame_segments() a déjà lues."""
from dataclasses import dataclass

from tms_vision.exercises import ZONES as _EXERCISE_ZONES
from tms_vision.exercises import load_catalog

ZONES = list(_EXERCISE_ZONES)
ZONE_PRIORITY = ["trunk", "neck", "upper_arm", "lower_arm", "hand", "foot"]
# lower_arm ne peut structurellement jamais atteindre ces niveaux : son sous-score
# RULA brut est plafonné à 3 (classify_lower_arm, rula/scoring.py) alors que
# action_level() n'entre dans ELEVATED_LEVELS qu'à partir de 5 -- même racine que
# la limitation déjà documentée pour changement_immediat sur neck/trunk/upper_arm
# (plafond 6 contre seuil 7, voir README.md et le commit 989df73). Conséquence :
# le catalogue CAPSULES contient une entrée pour lower_arm, mais compute_worst_zone
# ne pourra jamais la sélectionner tant que les seuils par segment ne sont pas
# redéfinis -- accepté pour ce sprint, voir la spec
# docs/superpowers/specs/2026-09-22-capsule-zone-recommendation-design.md.
ELEVATED_LEVELS = {"investigation_et_changement_bientot", "changement_immediat"}
MAX_PROGRAM_SIZE = 3


@dataclass
class Capsule:
    zone: str
    title: str
    description: str
    video_url: str
    # "stretch" aujourd'hui ; la future correction du geste utilisera "gesture"
    # (voir la Partie D de docs/superpowers/specs/2026-10-21-recurrence-programme-etirements-design.md).
    kind: str = "stretch"
    id: str = ""
    # "draft" : exercice rédigé mais pas encore relu par l'ostéopathe ; "validated"
    # une fois `validated_by` / `validated_on` renseignés dans sa définition.
    status: str = "draft"


def capsule_from_exercise(exercise: dict) -> Capsule:
    return Capsule(
        zone=exercise["zone"],
        title=exercise["title"],
        description=exercise["description"],
        # URL stable de la vidéo générée (voir capsule_build.py) ; le fichier peut
        # ne pas exister encore : l'API le signale par `video_available`.
        video_url=f"/capsules/{exercise['id']}/video",
        kind="stretch",
        id=exercise["id"],
        status=exercise["status"],
    )


# Catalogue construit depuis exercises/*.json (voir exercises.py) : plus de liste
# écrite à la main ni d'URL factice.
CAPSULES: list[Capsule] = [capsule_from_exercise(exercise) for exercise in load_catalog()]


def _segment_column(zone: str) -> str:
    return f"{zone}_segment_action_level"


def frame_durations(frames: list[dict]) -> list[float]:
    """Durée attribuée à chaque frame : écart jusqu'au timestamp de la frame
    suivante (jamais négatif). Cas limites : une frame unique vaut 1.0 s, la
    dernière frame d'une séquence plus longue vaut 0.0 s."""
    durations = []
    for index, frame in enumerate(frames):
        if index + 1 < len(frames):
            next_timestamp = frames[index + 1]["timestamp_seconds"]
        else:
            next_timestamp = None

        # Simplification délibérée par rapport à export.py.summary() : ce dernier garde
        # un fallback `or (1.0 if len(detected) == 1 else 0.0)` dans sa branche `else`
        # parce qu'il compte les frames *détectées*, un total différent de len(frames)
        # ici. Ici, la branche `else` n'est atteinte que si `index + 1 < len(frames)`,
        # ce qui implique `len(frames) >= 2` -- le fallback y vaudrait donc toujours
        # 0.0, identique à `max(...)` seul. Pas besoin de distinguer les frames
        # non détectées séparément : un segment_action_level à `None` exclut déjà
        # naturellement la frame de tout cumul de zone.
        if next_timestamp is None:
            durations.append(1.0 if len(frames) == 1 else 0.0)
        else:
            durations.append(max(next_timestamp - frame["timestamp_seconds"], 0.0))
    return durations


def elevated_seconds_by_zone(frames: list[dict]) -> dict[str, float]:
    """Temps cumulé passé dans les niveaux élevés, par zone."""
    cumulative_seconds = {zone: 0.0 for zone in ZONES}
    for frame, duration in zip(frames, frame_durations(frames)):
        for zone in ZONES:
            if frame[_segment_column(zone)] in ELEVATED_LEVELS:
                cumulative_seconds[zone] += duration
    return cumulative_seconds


def compute_worst_zone(frames: list[dict]) -> str | None:
    ranked = rank_zones(elevated_seconds_by_zone(frames), limit=1)
    return ranked[0][0] if ranked else None


def rank_zones(load_by_zone: dict[str, float], limit: int = MAX_PROGRAM_SIZE) -> list[tuple[str, float]]:
    """Zones à charge strictement positive, de la plus chargée à la moins chargée
    (égalité : ordre fixe ZONE_PRIORITY), tronquées à `limit`. Une zone absente
    du dictionnaire compte pour 0."""
    loaded = [
        (zone, load_by_zone.get(zone, 0.0))
        for zone in ZONE_PRIORITY
        if load_by_zone.get(zone, 0.0) > 0
    ]
    # sorted() est stable : à charge égale, l'ordre de ZONE_PRIORITY est conservé.
    return sorted(loaded, key=lambda item: -item[1])[:limit]


def recommend_capsule(zone: str | None) -> Capsule | None:
    if zone is None:
        return None
    for capsule in CAPSULES:
        if capsule.zone == zone:
            return capsule
    return None


def capsule_to_dict(capsule: Capsule) -> dict:
    return {
        "id": capsule.id,
        "zone": capsule.zone,
        "kind": capsule.kind,
        "status": capsule.status,
        "title": capsule.title,
        "description": capsule.description,
        "video_url": capsule.video_url,
    }
