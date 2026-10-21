from tms_vision.capsules import (
    CAPSULES,
    ZONE_PRIORITY,
    ZONES,
    MAX_PROGRAM_SIZE,
    capsule_to_dict,
    compute_worst_zone,
    elevated_seconds_by_zone,
    frame_durations,
    rank_zones,
    recommend_capsule,
)


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


def test_compute_worst_zone_prefers_longer_exposure_over_priority_order():
    frames = [
        _frame(0, 0.0, neck="changement_immediat", trunk="changement_immediat"),
        _frame(1, 1.0, neck="changement_immediat"),
        _frame(2, 2.0, neck="changement_immediat"),
        _frame(3, 3.0),
    ]
    # neck cumule 3.0s (frames 0,1,2) contre 1.0s pour trunk (frame 0 seule) --
    # neck doit gagner malgré son rang inférieur dans ZONE_PRIORITY (trunk >
    # neck), preuve que le départage est bien "durée cumulée d'abord, priorité
    # seulement en cas d'égalité stricte" et non "premier dégradé par ordre de priorité".
    assert compute_worst_zone(frames) == "neck"


def test_zones_and_zone_priority_contain_the_same_members():
    assert set(ZONES) == set(ZONE_PRIORITY)


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


def test_frame_durations_empty_single_and_multiple_frames():
    assert frame_durations([]) == []
    assert frame_durations([_frame(0, 5.0)]) == [1.0]
    frames = [_frame(0, 0.0), _frame(1, 0.5), _frame(2, 2.0)]
    assert frame_durations(frames) == [0.5, 1.5, 0.0]


def test_frame_durations_clamps_negative_gaps_to_zero():
    frames = [_frame(0, 2.0), _frame(1, 1.0)]
    assert frame_durations(frames) == [0.0, 0.0]


def test_elevated_seconds_by_zone_accumulates_only_elevated_levels():
    frames = [
        _frame(0, 0.0, trunk="changement_immediat", neck="investigation_recommandee"),
        _frame(1, 2.0, trunk="investigation_et_changement_bientot", neck="acceptable"),
        _frame(2, 5.0, trunk="acceptable"),
    ]

    seconds = elevated_seconds_by_zone(frames)

    assert seconds == {"neck": 0.0, "trunk": 5.0, "upper_arm": 0.0, "lower_arm": 0.0}


def test_compute_worst_zone_still_agrees_with_elevated_seconds_by_zone():
    frames = [
        _frame(0, 0.0, neck="changement_immediat"),
        _frame(1, 3.0, neck="acceptable", trunk="changement_immediat"),
        _frame(2, 4.0, trunk="acceptable"),
    ]

    assert compute_worst_zone(frames) == "neck"


def test_rank_zones_sorts_by_load_descending():
    ranked = rank_zones({"neck": 10.0, "trunk": 30.0, "upper_arm": 20.0, "lower_arm": 0.0})

    assert ranked == [("trunk", 30.0), ("upper_arm", 20.0), ("neck", 10.0)]


def test_rank_zones_breaks_ties_with_the_fixed_zone_priority():
    ranked = rank_zones({"neck": 5.0, "trunk": 5.0, "upper_arm": 5.0, "lower_arm": 5.0})

    assert [zone for zone, _ in ranked] == ["trunk", "neck", "upper_arm"]


def test_rank_zones_excludes_zero_load_and_caps_the_program_size():
    ranked = rank_zones({"neck": 1.0, "trunk": 2.0, "upper_arm": 3.0, "lower_arm": 4.0})

    assert MAX_PROGRAM_SIZE == 3
    assert len(ranked) == 3
    assert [zone for zone, _ in ranked] == ["lower_arm", "upper_arm", "trunk"]
    assert rank_zones({zone: 0.0 for zone in ZONES}) == []
    assert rank_zones({}) == []


def test_every_catalog_capsule_is_a_stretch_for_now():
    assert {capsule.kind for capsule in CAPSULES} == {"stretch"}


def test_capsule_to_dict_exposes_kind_and_content():
    capsule = recommend_capsule("trunk")

    assert capsule_to_dict(capsule) == {
        "zone": "trunk", "kind": "stretch", "title": capsule.title,
        "description": capsule.description, "video_url": capsule.video_url,
    }
