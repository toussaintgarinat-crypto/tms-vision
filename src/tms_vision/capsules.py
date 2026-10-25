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
# Nombre d'exercices proposés par défaut ; le praticien le règle bilan par bilan (3, 5, 10...).
DEFAULT_PROGRAM_SIZE = 5
MAX_PROGRAM_SIZE = 20  # plafond du nombre d'exercices qu'on peut demander


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
    # Position de l'exercice (standing, seated, lying) et segments du squelette qu'il fait travailler.
    position: str = "standing"
    target_segments: tuple[str, ...] = ()
    # Ce que l'exercice apporte, en une phrase (vide quand l'exercice n'en donne pas).
    benefit: str = ""


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
        position=exercise.get("position", "standing"),
        target_segments=tuple(exercise["target_segments"]),
        benefit=exercise.get("benefit", ""),
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


def rank_zones(load_by_zone: dict[str, float], limit: int | None = None) -> list[tuple[str, float]]:
    """Zones à charge strictement positive, de la plus chargée à la moins chargée
    (égalité : ordre fixe ZONE_PRIORITY), tronquées à `limit` si donné. Une zone absente
    du dictionnaire compte pour 0."""
    loaded = [
        (zone, load_by_zone.get(zone, 0.0))
        for zone in ZONE_PRIORITY
        if load_by_zone.get(zone, 0.0) > 0
    ]
    # sorted() est stable : à charge égale, l'ordre de ZONE_PRIORITY est conservé.
    return sorted(loaded, key=lambda item: -item[1])[:limit]


# Exercice recommandé par le programme d'étirements pour chaque zone RULA. Le catalogue contient
# aussi les exercices de la bibliothèque du praticien (voir library.py) : sans ce choix explicite,
# ajouter un exercice à une zone changerait la recommandation faite aux salariés.
PROGRAM_CAPSULE_BY_ZONE = {
    "neck": "neck-lateral-stretch",
    "trunk": "trunk-lumbar-mobility",
    "upper_arm": "shoulder-cross-body-stretch",
    "lower_arm": "forearm-extension-stretch",
    "hand": "finger-extension-stretch",
    "foot": "ankle-mobility",
}


# Équivalents assis des exercices du programme, pour un poste de travail assis (voir
# bilan.preferred_position). Pas d'entrée pour `foot` : « ankle-mobility » se fait déjà assis.
SEATED_CAPSULE_BY_ZONE = {
    "neck": "seated-neck-lateral-stretch",
    "trunk": "seated-round-hollow-back",
    "upper_arm": "seated-shoulder-cross-body-stretch",
    "lower_arm": "seated-forearm-extension-stretch",
    "hand": "seated-wrist-flexor-stretch",
}


def recommend_capsule(zone: str | None, position: str | None = None) -> Capsule | None:
    """Exercice du programme pour une zone. `position="seated"` : son équivalent assis quand il existe."""
    if zone is None:
        return None
    preferred = PROGRAM_CAPSULE_BY_ZONE.get(zone)
    if position == "seated":
        preferred = SEATED_CAPSULE_BY_ZONE.get(zone, preferred)
    for capsule in CAPSULES:
        if capsule.id == preferred:
            return capsule
    for capsule in CAPSULES:
        if capsule.zone == zone:
            return capsule
    return None


def candidate_capsules(zone: str, position: str | None = None) -> list[Capsule]:
    """Exercices utilisables pour une zone, du plus adapté au moins adapté : d'abord l'exercice
    habituel du programme, puis les autres de la zone dans la position du poste (assis pour un
    poste assis, debout sinon), puis ceux de l'autre position. Les exercices allongés sont exclus :
    ils ne se font pas sur un poste de travail."""
    first = recommend_capsule(zone, position)
    wanted = "seated" if position == "seated" else "standing"
    others = [
        capsule for capsule in CAPSULES
        if capsule.zone == zone and capsule.position != "lying" and capsule is not first
    ]
    others.sort(key=lambda capsule: (capsule.position != wanted, capsule.id))
    return ([first] if first is not None else []) + others


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
