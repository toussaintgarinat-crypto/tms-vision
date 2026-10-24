import pytest

from tms_vision.program import (
    build_analysis_program,
    build_bilan_program,
    describe_load,
    format_hours,
    format_seconds,
)


def _frame(index, timestamp, **levels):
    row = {
        "frame_index": index, "timestamp_seconds": timestamp,
        "neck_segment_action_level": None, "trunk_segment_action_level": None,
        "upper_arm_segment_action_level": None, "lower_arm_segment_action_level": None,
        "hand_segment_action_level": None, "foot_segment_action_level": None,
    }
    for zone, level in levels.items():
        row[f"{zone}_segment_action_level"] = level
    return row


NO_LOAD = {"kind": "exact", "kg": 0.0, "kg_min": None, "kg_max": None}


@pytest.mark.parametrize(
    "seconds, expected",
    [(0, "0 s"), (42, "42 s"), (59.6, "1 min"), (60, "1 min"), (90, "1 min 30"), (125, "2 min 05")],
)
def test_format_seconds(seconds, expected):
    assert format_seconds(seconds) == expected


@pytest.mark.parametrize(
    "hours, expected",
    [(0, "0 min"), (0.5, "30 min"), (5, "5 h"), (4.2, "4 h 12"), (1.05, "1 h 03"), (1.9933, "2 h")],
)
def test_format_hours(hours, expected):
    assert format_hours(hours) == expected


def test_describe_load_covers_every_kind():
    assert describe_load({"kind": "exact", "kg": 12.0, "kg_min": None, "kg_max": None}) == "12 kg"
    assert describe_load({"kind": "exact", "kg": 7.5, "kg_min": None, "kg_max": None}) == "7,5 kg"
    assert describe_load({"kind": "range", "kg": None, "kg_min": 8.0, "kg_max": 12.0}) == "8 à 12 kg"
    assert describe_load({"kind": "range", "kg": None, "kg_min": 5.0, "kg_max": 5.0}) == "5 kg"
    assert describe_load({"kind": "none", "kg": None, "kg_min": None, "kg_max": None}) is None
    assert describe_load(NO_LOAD) is None
    assert describe_load(None) is None


def test_analysis_program_ranks_zones_by_elevated_time_and_numbers_them():
    frames = [
        _frame(0, 0.0, trunk="changement_immediat", neck="changement_immediat"),
        _frame(1, 3.0, trunk="changement_immediat", neck="acceptable"),
        _frame(2, 4.0, trunk="acceptable"),
    ]

    program = build_analysis_program(frames, NO_LOAD)

    assert [item["zone"] for item in program] == ["trunk", "neck"]
    assert [item["rank"] for item in program] == [1, 2]
    assert program[0]["capsule"]["zone"] == "trunk"
    assert program[0]["capsule"]["kind"] == "stretch"
    assert program[0]["load"] == 4.0
    assert program[0]["reason"] == "Tronc : 4 s en posture à risque sur l'échantillon."
    assert program[1]["reason"] == "Cou : 3 s en posture à risque sur l'échantillon."


def test_analysis_program_mentions_the_load_when_one_is_entered():
    frames = [_frame(0, 0.0, trunk="changement_immediat"), _frame(1, 2.0)]
    load = {"kind": "range", "kg": None, "kg_min": 8.0, "kg_max": 12.0}

    program = build_analysis_program(frames, load)

    assert program[0]["reason"] == (
        "Tronc : 2 s en posture à risque sur l'échantillon (charge manipulée : 8 à 12 kg)."
    )


def test_analysis_program_is_empty_when_no_zone_is_at_risk():
    frames = [_frame(0, 0.0, trunk="acceptable"), _frame(1, 1.0, trunk="investigation_recommandee")]

    assert build_analysis_program(frames, NO_LOAD) == []


def test_analysis_program_is_capped_at_three_capsules():
    frames = [
        _frame(0, 0.0, neck="changement_immediat", trunk="changement_immediat",
               upper_arm="changement_immediat", lower_arm="changement_immediat"),
        _frame(1, 1.0),
    ]

    program = build_analysis_program(frames, NO_LOAD)

    assert len(program) == 3
    assert [item["zone"] for item in program] == ["trunk", "neck", "upper_arm"]


def _report(**hours_by_zone):
    zones = {
        zone: {"projected_cycles": 0.0, "projected_elevated_hours": hours_by_zone.get(zone, 0.0)}
        for zone in ("neck", "trunk", "upper_arm", "lower_arm")
    }
    return {"workday_hours": 9.0, "zones": zones, "warnings": ["avertissement"]}


def test_bilan_program_ranks_zones_by_projected_hours():
    program = build_bilan_program(_report(trunk=4.2, upper_arm=1.5, neck=0.5))

    assert [item["zone"] for item in program] == ["trunk", "upper_arm", "neck"]
    assert program[0]["reason"] == (
        "Tronc : environ 4 h 12 en posture à risque sur 9 h estimées."
    )
    assert program[0]["load"] == 4.2
    assert program[0]["rank"] == 1


def test_bilan_program_is_empty_without_any_projected_risk():
    assert build_bilan_program(_report()) == []


def test_hand_and_foot_can_be_recommended_with_their_own_labels():
    frames = [
        _frame(0, 0.0, hand="investigation_et_changement_bientot"),
        _frame(1, 10.0, hand="investigation_et_changement_bientot", foot="investigation_et_changement_bientot"),
        _frame(2, 12.0),
    ]
    program = build_analysis_program(frames, None)
    assert [item["zone"] for item in program] == ["hand", "foot"]
    assert program[0]["capsule"]["zone"] == "hand"
    assert program[0]["reason"].startswith("Main / poignet : 12 s")
    assert program[1]["reason"].startswith("Pied / cheville : 2 s")


def test_bilan_program_uses_seated_exercises_for_a_seated_workstation_and_keeps_the_ranking():
    report = _report(trunk=4.2, upper_arm=1.5, neck=0.5)

    standard = build_bilan_program(report)
    seated = build_bilan_program(report, "seated")

    assert [item["zone"] for item in seated] == [item["zone"] for item in standard]
    assert [item["capsule"]["id"] for item in seated] == [
        "seated-round-hollow-back", "seated-shoulder-cross-body-stretch", "seated-neck-lateral-stretch",
    ]
    assert [item["capsule"]["id"] for item in standard] != [item["capsule"]["id"] for item in seated]
    assert [item["reason"] for item in seated] == [item["reason"] for item in standard]


def _task(name, zones, hours, analysis_id=None):
    return {"name": name, "zones": zones, "activity_hours": hours, "analysis_id": analysis_id}


def test_bilan_program_without_video_is_built_from_the_declared_tasks():
    tasks = [
        _task("Saisie", ["neck", "hand"], 4.5),
        _task("Réunions", ["neck", "trunk"], 1.5),
        _task("Classement", ["trunk"], 1.0),
    ]

    program = build_bilan_program(_report(), None, tasks)

    # Cou : 6 h, tronc : 2 h 30, main : 4 h 30 → cou, main, tronc.
    assert [item["zone"] for item in program] == ["neck", "hand", "trunk"]
    assert [item["rank"] for item in program] == [1, 2, 3]
    assert {item["basis"] for item in program} == {"declared"}
    assert program[0]["load"] == 6.0
    assert program[0]["reason"] == (
        "Cou : environ 6 h de tâches qui la sollicitent, surtout « Saisie » "
        "(d'après les tâches saisies, sans mesure vidéo)."
    )


def test_bilan_program_puts_measured_zones_first_and_never_repeats_a_zone():
    tasks = [_task("Saisie", ["neck", "hand"], 4.5), _task("Port", ["trunk", "foot"], 1.0)]

    program = build_bilan_program(_report(trunk=2.0), None, tasks)

    assert [item["zone"] for item in program] == ["trunk", "neck", "hand"]
    assert [item["basis"] for item in program] == ["measured", "declared", "declared"]


def test_bilan_program_ignores_tasks_completing_a_video_and_stays_empty_without_tasks():
    assert build_bilan_program(_report(), None, [_task("Vissage", ["hand"], 2.0, "a-1")]) == []
    assert build_bilan_program(_report(), None, []) == []


def test_declared_program_follows_the_seated_position():
    tasks = [_task("Saisie", ["neck"], 4.5)]

    seated = build_bilan_program(_report(), "seated", tasks)
    standard = build_bilan_program(_report(), None, tasks)

    assert seated[0]["capsule"]["id"] == "seated-neck-lateral-stretch"
    assert standard[0]["capsule"]["id"] == "neck-lateral-stretch"
