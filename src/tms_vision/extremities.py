"""Mesure de la main et du pied par vidéo (Tranche 5, voir
docs/superpowers/specs/2026-10-22-mains-pieds-design.md).

RULA ne note que le poignet ; la main (poignet + doigts) et le pied (cheville) sont notés ici avec
la même échelle de 1 (neutre) à 3 (écart marqué), puis convertis en niveau d'action. Ces notes ne
modifient pas le score RULA final : elles n'alimentent que les niveaux par segment, donc la
coloration de l'avatar, la récurrence et le programme d'étirements.

Aucun seuil n'est codé ici : ils sont lus dans extremity_thresholds.json, à calibrer avec
l'ostéopathe (voir `calibrated`). Module pur."""
import json
from pathlib import Path

import numpy as np

from tms_vision.rula.scoring import classify_wrist

THRESHOLDS_PATH = Path(__file__).with_name("extremity_thresholds.json")
EXTREMITY_ZONES = ("hand", "foot")
LEVELS = (
    "acceptable",
    "investigation_recommandee",
    "investigation_et_changement_bientot",
    "changement_immediat",
)

# Doigts longs (index, majeur, annulaire, auriculaire) : MCP, PIP, DIP dans les 21 points de
# MediaPipe Hands.
FINGER_JOINTS = ((5, 6, 7), (9, 10, 11), (13, 14, 15), (17, 18, 19))


def load_extremity_thresholds(path: Path | str | None = None) -> dict:
    with open(path or THRESHOLDS_PATH) as f:
        raw = json.load(f)
    for zone, key in (("hand", "finger_curl_bounds_deg"), ("foot", "ankle_bounds_deg")):
        section = raw.get(zone, {})
        bounds = section.get(key)
        cutoffs = section.get("level_cutoffs")
        if not (isinstance(bounds, list) and len(bounds) == 2 and bounds[0] <= bounds[1]):
            raise ValueError(f"Seuils invalides pour la zone '{zone}' : '{key}' attend [bas, haut].")
        if not (isinstance(cutoffs, list) and len(cutoffs) == 3 and cutoffs == sorted(cutoffs)):
            raise ValueError(
                f"Seuils invalides pour la zone '{zone}' : 'level_cutoffs' attend trois notes croissantes."
            )
    return {"calibrated": bool(raw.get("calibrated", False)), "hand": raw["hand"], "foot": raw["foot"]}


def _angle_between(v1: np.ndarray, v2: np.ndarray) -> float:
    norm_product = np.linalg.norm(v1) * np.linalg.norm(v2)
    if norm_product == 0:
        return 0.0
    return float(np.degrees(np.arccos(np.clip(np.dot(v1, v2) / norm_product, -1.0, 1.0))))


def finger_curl_deg(hand_points: list[tuple[float, float]], aspect: float = 1.0) -> float | None:
    """Flexion moyenne des quatre doigts longs à l'articulation médiane (0° = doigt tendu,
    90° = poing). `hand_points` : les 21 points MediaPipe Hands normalisés (x, y) ; `aspect` =
    largeur / hauteur de l'image, pour ne pas déformer les angles."""
    if len(hand_points) != 21:
        return None
    pts = np.array([[x * aspect, y] for x, y in hand_points])
    curls = [180.0 - _angle_between(pts[a] - pts[b], pts[c] - pts[b]) for a, b, c in FINGER_JOINTS]
    return float(np.mean(curls))


def _band(value: float, bounds: list[float]) -> int:
    if value <= bounds[0]:
        return 1
    if value <= bounds[1]:
        return 2
    return 3


def classify_hand(wrist_flexion: float | None, curl: float | None, thresholds: dict) -> int | None:
    """1 à 3 : le pire de la flexion du poignet (mêmes bornes que RULA) et de la flexion des
    doigts. `None` quand ni l'un ni l'autre n'est mesuré."""
    scores = []
    if wrist_flexion is not None:
        scores.append(min(classify_wrist(wrist_flexion, False), 3))
    if curl is not None:
        scores.append(_band(abs(curl), thresholds["hand"]["finger_curl_bounds_deg"]))
    return max(scores) if scores else None


def classify_foot(ankle_deviation: float | None, thresholds: dict) -> int | None:
    if ankle_deviation is None:
        return None
    return _band(abs(ankle_deviation), thresholds["foot"]["ankle_bounds_deg"])


def extremity_action_level(zone: str, score: int | None, thresholds: dict) -> str | None:
    if score is None:
        return None
    acceptable_max, recommended_max, soon_max = thresholds[zone]["level_cutoffs"]
    if score <= acceptable_max:
        return LEVELS[0]
    if score <= recommended_max:
        return LEVELS[1]
    if score <= soon_max:
        return LEVELS[2]
    return LEVELS[3]
