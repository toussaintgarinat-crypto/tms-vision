"""Recalcul des scores RULA d'une analyse terminée pour un autre poids, sans
relancer l'estimation de pose (voir
docs/superpowers/plans/2026-10-21-poids-programme-capsules-plan.md).

Le poids n'intervient que dans `force_load_score` : ensuite
`wrist_arm_score = posture_score_a + muscle_use_score + force`,
`neck_trunk_leg_score = posture_score_b + muscle_use_score + force`, puis
`final_score` (table C) et `action_level`. Les trois colonnes `posture_score_a`,
`posture_score_b` et `muscle_use_score`, déjà persistées par frame, suffisent
donc à reproduire exactement `rula.scoring.compute_rula_score`. Les niveaux
d'action par segment (neck/trunk/upper_arm/lower_arm) ne dépendent pas du
poids et ne sont pas recalculés. Module pur, sans accès à la base."""
from tms_vision.export import summarize_rows
from tms_vision.rula.scoring import action_level, force_load_score
from tms_vision.rula.tables import lookup_table_c


def rescore_frames(frames: list[dict], load_kg: float) -> list[dict]:
    """Chaque frame d'entrée porte frame_index, timestamp_seconds, detected,
    posture_score_a, posture_score_b et muscle_use_score. Les frames sans
    score (posture_score_a None) gardent des valeurs None."""
    rescored = []
    for frame in frames:
        row = dict(frame)
        has_score = (
            frame["posture_score_a"] is not None
            and frame["posture_score_b"] is not None
            and frame["muscle_use_score"] is not None
        )
        if not has_score:
            row.update(force_load_score=None, final_score=None, action_level=None)
        else:
            muscle_use = frame["muscle_use_score"]
            force = force_load_score(load_kg, muscle_use == 1)
            wrist_arm_score = frame["posture_score_a"] + muscle_use + force
            neck_trunk_leg_score = frame["posture_score_b"] + muscle_use + force
            final_score = lookup_table_c(wrist_arm_score, neck_trunk_leg_score)
            row.update(
                force_load_score=force,
                final_score=final_score,
                action_level=action_level(final_score),
            )
        rescored.append(row)
    return rescored


def summarize_for_load(frames: list[dict], load_kg: float) -> dict:
    return summarize_rows(rescore_frames(frames, load_kg))
