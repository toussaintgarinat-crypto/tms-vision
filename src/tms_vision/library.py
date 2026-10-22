"""Bibliothèque d'exercices pour le professionnel de santé : la carte du corps
(`library/body_map.json`) range les exercices du catalogue par zone puis par
pathologie. Le contenu médical de ce fichier est un brouillon tant qu'un professionnel de
santé ne l'a pas relu (champ `status`)."""
import json
from pathlib import Path

from tms_vision import exercises

LIBRARY_PATH = Path(__file__).resolve().parents[2] / "library" / "body_map.json"


def _fail(field: str, message: str) -> None:
    raise ValueError(f"{field} : {message}")


def validate_library(data: dict, exercise_ids: set[str]) -> None:
    """Lève ValueError, avec un message en français nommant le champ fautif, si la carte du
    corps est invalide ou référence un exercice absent du catalogue."""
    if not isinstance(data, dict):
        _fail("bibliothèque", "objet JSON attendu.")
    if data.get("status") not in exercises.STATUSES:
        _fail("status", f"valeur attendue parmi {', '.join(exercises.STATUSES)}.")
    zones = data.get("zones")
    if not isinstance(zones, list) or not zones:
        _fail("zones", "au moins une zone attendue.")

    seen_zones: set[str] = set()
    seen_pathologies: set[str] = set()
    for zone in zones:
        zone_id = zone.get("id") if isinstance(zone, dict) else None
        if not isinstance(zone_id, str) or not zone_id:
            _fail("zones", "chaque zone exige un id texte.")
        if zone_id in seen_zones:
            _fail(f"zones[{zone_id}]", "id en double.")
        seen_zones.add(zone_id)
        if not isinstance(zone.get("label"), str) or not zone["label"].strip():
            _fail(f"zones[{zone_id}].label", "texte non vide attendu.")
        pathologies = zone.get("pathologies")
        if not isinstance(pathologies, list) or not pathologies:
            _fail(f"zones[{zone_id}].pathologies", "au moins une pathologie attendue.")
        for pathology in pathologies:
            pathology_id = pathology.get("id") if isinstance(pathology, dict) else None
            if not isinstance(pathology_id, str) or not pathology_id:
                _fail(f"zones[{zone_id}].pathologies", "chaque pathologie exige un id texte.")
            if pathology_id in seen_pathologies:
                _fail(f"pathologies[{pathology_id}]", "id en double.")
            seen_pathologies.add(pathology_id)
            if not isinstance(pathology.get("label"), str) or not pathology["label"].strip():
                _fail(f"pathologies[{pathology_id}].label", "texte non vide attendu.")
            listed = pathology.get("exercises")
            if not isinstance(listed, list) or not listed:
                _fail(f"pathologies[{pathology_id}].exercises", "au moins un exercice attendu.")
            if len(set(listed)) != len(listed):
                _fail(f"pathologies[{pathology_id}].exercises", "exercices en double.")
            for exercise_id in listed:
                if exercise_id not in exercise_ids:
                    _fail(
                        f"pathologies[{pathology_id}].exercises",
                        f"exercice inconnu '{exercise_id}' (absent du catalogue).",
                    )


def load_library(
    path: Path | str | None = None, catalog: list[dict] | None = None
) -> dict:
    path = Path(path) if path is not None else LIBRARY_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{path.name} : JSON invalide ({error}).") from error
    catalog = catalog if catalog is not None else exercises.load_catalog()
    try:
        validate_library(data, {exercise["id"] for exercise in catalog})
    except ValueError as error:
        raise ValueError(f"{path.name} : {error}") from error
    return data
