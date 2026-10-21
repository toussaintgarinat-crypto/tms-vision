"""Poids manipulé, saisi par l'opérateur après l'analyse vidéo (la vidéo ne
peut pas le deviner) : aucun, précis, ou en fourchette (voir
docs/superpowers/specs/2026-10-21-recurrence-programme-etirements-design.md).
Module pur : validation et bornes, aucun accès à la base ni au scoring."""
from dataclasses import dataclass

MAX_LOAD_KG = 500.0
KINDS = ("none", "exact", "range")


@dataclass(frozen=True)
class Load:
    kind: str
    kg: float | None
    kg_min: float | None
    kg_max: float | None


def _check_weight(name: str, value: float) -> float:
    if value < 0:
        raise ValueError(f"{name} ne peut pas être négatif.")
    if value > MAX_LOAD_KG:
        raise ValueError(f"{name} dépasse {MAX_LOAD_KG:g} kg.")
    return float(value)


def parse_load(
    kind: str,
    kg: float | None = None,
    kg_min: float | None = None,
    kg_max: float | None = None,
) -> Load:
    if kind not in KINDS:
        raise ValueError(f"Type de poids inconnu : '{kind}'.")

    if kind == "none":
        if kg is not None or kg_min is not None or kg_max is not None:
            raise ValueError("Aucun poids ne doit être renseigné quand le type est 'none'.")
        return Load(kind="none", kg=None, kg_min=None, kg_max=None)

    if kind == "exact":
        if kg is None:
            raise ValueError("Le poids précis est requis.")
        if kg_min is not None or kg_max is not None:
            raise ValueError("Un poids précis n'a pas de bornes.")
        return Load(kind="exact", kg=_check_weight("Le poids", kg), kg_min=None, kg_max=None)

    if kg_min is None or kg_max is None:
        raise ValueError("Les deux bornes de la fourchette sont requises.")
    if kg is not None:
        raise ValueError("Une fourchette n'a pas de poids précis.")
    low = _check_weight("La borne basse", kg_min)
    high = _check_weight("La borne haute", kg_max)
    if low > high:
        raise ValueError("La borne basse ne peut pas dépasser la borne haute.")
    return Load(kind="range", kg=None, kg_min=low, kg_max=high)


def bounds(load: Load) -> tuple[float, float]:
    """(bas, haut) en kg ; sans poids, 0 kg aux deux bornes."""
    if load.kind == "exact":
        return (load.kg, load.kg)
    if load.kind == "range":
        return (load.kg_min, load.kg_max)
    return (0.0, 0.0)
