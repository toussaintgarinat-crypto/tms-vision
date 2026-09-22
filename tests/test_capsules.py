from tms_vision.capsules import CAPSULES, ZONES, compute_worst_zone, recommend_capsule


def _frame(frame_index, timestamp_seconds, **levels):
    row = {
        "frame_index": frame_index,
        "timestamp_seconds": timestamp_seconds,
        "neck_segment_action_level": None,
        "trunk_segment_action_level": None,
        "upper_arm_segment_action_level": None,
        "lower_arm_segment_action_level": None,
    }
    for zone, level in levels.items():
        row[f"{zone}_segment_action_level"] = level
    return row


def test_compute_worst_zone_picks_zone_with_most_cumulative_time_in_elevated_levels():
    frames = [
        _frame(0, 0.0, trunk="changement_immediat", neck="acceptable"),
        _frame(1, 1.0, trunk="changement_immediat", neck="acceptable"),
        _frame(2, 2.0, trunk="acceptable", neck="investigation_et_changement_bientot"),
        _frame(3, 3.0, trunk="acceptable", neck="acceptable"),
    ]
    # trunk dégradé sur [0,1] -> 2.0s cumulées ; neck dégradé sur [2,3) -> 1.0s cumulée.
    assert compute_worst_zone(frames) == "trunk"


def test_compute_worst_zone_returns_none_when_nothing_is_degraded():
    frames = [
        _frame(0, 0.0, trunk="acceptable", neck="investigation_recommandee"),
        _frame(1, 1.0, trunk="acceptable", neck="acceptable"),
    ]
    # investigation_recommandee ne compte pas comme "dégradé".
    assert compute_worst_zone(frames) is None


def test_compute_worst_zone_breaks_exact_ties_by_fixed_priority_order():
    frames = [
        _frame(
            0, 0.0,
            trunk="changement_immediat", neck="changement_immediat",
            upper_arm="changement_immediat", lower_arm="changement_immediat",
        ),
        _frame(1, 1.0),
    ]
    # Les 4 zones cumulent exactement 1.0s chacune -> égalité stricte, trunk gagne (priorité).
    assert compute_worst_zone(frames) == "trunk"


def test_compute_worst_zone_ignores_undetected_frames_for_cumulation_but_uses_their_timestamp():
    frames = [
        _frame(0, 0.0, trunk="changement_immediat"),
        _frame(1, 1.0),  # non détectée : tous les niveaux à None
        _frame(2, 5.0, trunk="acceptable"),
    ]
    # trunk dégradé seulement sur la frame 0, durée jusqu'à la frame 1 (non détectée) = 1.0s.
    assert compute_worst_zone(frames) == "trunk"


def test_compute_worst_zone_handles_empty_frame_list():
    assert compute_worst_zone([]) is None


def test_recommend_capsule_returns_first_catalog_entry_for_the_zone():
    capsule = recommend_capsule("neck")
    assert capsule is not None
    assert capsule.zone == "neck"
    assert capsule == next(c for c in CAPSULES if c.zone == "neck")


def test_recommend_capsule_returns_none_for_none_zone():
    assert recommend_capsule(None) is None


def test_catalog_has_at_least_one_capsule_per_measured_zone():
    catalog_zones = {c.zone for c in CAPSULES}
    assert set(ZONES) <= catalog_zones
