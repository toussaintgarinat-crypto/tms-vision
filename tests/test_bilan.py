import pytest

from tms_vision.bilan import SHORT_SAMPLE_SECONDS, project_bilan
from tms_vision.capsules import ZONES


def _recurrence(sample_seconds=180.0, calibrated=False, **zone_values):
    zones = {
        zone: {
            "cycles": 0.0,
            "cycles_per_minute": 0.0,
            "mean_cycle_seconds": None,
            "longest_static_seconds": 0.0,
            "elevated_seconds": 0.0,
            "assessment": None,
        }
        for zone in ZONES
    }
    for zone, values in zone_values.items():
        zones[zone].update(values)
    return {"sample_seconds": sample_seconds, "thresholds_calibrated": calibrated, "zones": zones}


def _item(analysis_id, activity_hours, representative=True, recurrence=None):
    return {
        "analysis_id": analysis_id,
        "activity_hours": activity_hours,
        "representative": representative,
        "recurrence": recurrence or _recurrence(),
    }


def test_projected_cycles_weight_each_analysis_by_its_activity_hours():
    items = [
        _item("a", 5.0, recurrence=_recurrence(trunk={"cycles_per_minute": 3.0})),
        _item("b", 3.0, recurrence=_recurrence(trunk={"cycles_per_minute": 6.0})),
    ]

    report = project_bilan(9.0, items)

    assert report["zones"]["trunk"]["projected_cycles"] == 3 * 60 * 5 + 6 * 60 * 3
    assert report["zones"]["neck"]["projected_cycles"] == 0.0


def test_projected_elevated_hours_scale_the_measured_share_to_the_activity():
    # 90 s sur 180 s en niveau eleve = 50 % ; sur 6 h d'activite -> 3 h.
    items = [
        _item("a", 6.0, recurrence=_recurrence(
            sample_seconds=180.0, trunk={"elevated_seconds": 90.0})),
    ]

    report = project_bilan(9.0, items)

    assert report["zones"]["trunk"]["projected_elevated_hours"] == 3.0


def test_non_representative_analysis_is_listed_but_excluded_from_sums():
    items = [
        _item("a", 5.0, recurrence=_recurrence(trunk={"cycles_per_minute": 3.0})),
        _item("b", 3.0, representative=False,
              recurrence=_recurrence(trunk={"cycles_per_minute": 100.0})),
    ]

    report = project_bilan(9.0, items)

    assert report["zones"]["trunk"]["projected_cycles"] == 3 * 60 * 5
    by_id = {a["analysis_id"]: a for a in report["analyses"]}
    assert by_id["a"]["included"] is True
    assert by_id["b"]["included"] is False
    assert by_id["b"]["recurrence"]["zones"]["trunk"]["cycles_per_minute"] == 100.0


def test_undocumented_hours_are_the_part_of_the_day_not_covered():
    report = project_bilan(9.0, [_item("a", 5.0), _item("b", 3.0)])

    assert report["documented_hours"] == 8.0
    assert report["undocumented_hours"] == 1.0
    assert report["workday_hours"] == 9.0


def test_short_sample_gets_a_warning():
    short = _recurrence(sample_seconds=SHORT_SAMPLE_SECONDS - 10)

    report = project_bilan(9.0, [_item("a", 2.0, recurrence=short)])

    assert len(report["analyses"][0]["warnings"]) == 1
    assert "court" in report["analyses"][0]["warnings"][0]


def test_long_enough_sample_has_no_warning():
    report = project_bilan(9.0, [_item("a", 2.0)])

    assert report["analyses"][0]["warnings"] == []


def test_documented_hours_above_workday_raise_value_error():
    with pytest.raises(ValueError):
        project_bilan(9.0, [_item("a", 6.0), _item("b", 4.0)])


@pytest.mark.parametrize("workday_hours, activity_hours", [(0.0, 1.0), (9.0, 0.0), (9.0, -1.0)])
def test_non_positive_hours_raise_value_error(workday_hours, activity_hours):
    with pytest.raises(ValueError):
        project_bilan(workday_hours, [_item("a", activity_hours)])


def test_empty_bilan_has_zero_projection_and_whole_day_undocumented():
    report = project_bilan(9.0, [])

    assert report["undocumented_hours"] == 9.0
    assert report["analyses"] == []
    assert report["thresholds_calibrated"] is False
    assert all(z["projected_cycles"] == 0.0 for z in report["zones"].values())
    assert any("représentative" in w for w in report["warnings"])


def test_no_representative_analysis_adds_a_global_warning():
    report = project_bilan(9.0, [_item("a", 2.0, representative=False)])

    assert any("représentative" in w for w in report["warnings"])


def test_zero_length_sample_contributes_nothing_to_the_projection():
    recurrence = _recurrence(
        sample_seconds=0.0, trunk={"cycles_per_minute": None, "elevated_seconds": 5.0})

    report = project_bilan(9.0, [_item("a", 2.0, recurrence=recurrence)])

    assert report["zones"]["trunk"]["projected_cycles"] == 0.0
    assert report["zones"]["trunk"]["projected_elevated_hours"] == 0.0


def test_thresholds_calibrated_only_when_every_analysis_reports_it():
    calibrated = _recurrence(calibrated=True)
    uncalibrated = _recurrence(calibrated=False)

    assert project_bilan(9.0, [_item("a", 2.0, recurrence=calibrated)])[
        "thresholds_calibrated"] is True
    assert project_bilan(9.0, [
        _item("a", 2.0, recurrence=calibrated), _item("b", 2.0, recurrence=uncalibrated),
    ])["thresholds_calibrated"] is False


def _task(task_id="t1", hours=2.0, zones=("upper_arm",), cpm=10.0, analysis_id=None,
          slots=None, source="practitioner", name="Peindre un plafond"):
    return {
        "id": task_id, "name": name, "zones": list(zones), "activity_hours": hours,
        "time_slots": slots, "cycles_per_minute": cpm, "analysis_id": analysis_id,
        "source": source,
    }


def test_standalone_task_adds_declared_cycles_and_counts_in_the_workday():
    report = project_bilan(9.0, [], [_task(hours=2.0, zones=("neck", "upper_arm"), cpm=10.0)])

    assert report["zones"]["upper_arm"]["projected_cycles"] == 10 * 60 * 2
    assert report["zones"]["neck"]["projected_cycles"] == 10 * 60 * 2
    assert report["zones"]["trunk"]["projected_cycles"] == 0.0
    assert report["documented_hours"] == 2.0
    assert report["undocumented_hours"] == 7.0
    [entry] = report["tasks"]
    assert entry["source"] == "practitioner"
    assert any("non mesurés" in warning for warning in entry["warnings"])
    # Sans vidéo : aucune heure en posture à risque n'est inventée.
    assert report["zones"]["upper_arm"]["projected_elevated_hours"] == 0.0
    assert report["warnings"] == []


def test_standalone_task_adds_to_video_cycles():
    items = [_item("a", 5.0, recurrence=_recurrence(trunk={"cycles_per_minute": 3.0}))]

    report = project_bilan(9.0, items, [_task(hours=2.0, zones=("trunk",), cpm=1.0)])

    assert report["zones"]["trunk"]["projected_cycles"] == 3 * 60 * 5 + 1 * 60 * 2
    assert report["documented_hours"] == 7.0


def test_task_completing_a_video_overrides_measure_but_keeps_it_visible():
    items = [_item("a", 5.0, recurrence=_recurrence(
        sample_seconds=180.0, trunk={"cycles_per_minute": 3.0, "elevated_seconds": 90.0},
        neck={"cycles_per_minute": 4.0}))]
    task = _task(hours=99.0, zones=("trunk",), cpm=8.0, analysis_id="a")

    report = project_bilan(9.0, items, [task])

    # La valeur saisie remplace la mesure du tronc ; le cou reste mesuré.
    assert report["zones"]["trunk"]["projected_cycles"] == 8 * 60 * 5
    assert report["zones"]["neck"]["projected_cycles"] == 4 * 60 * 5
    # La durée est celle de la vidéo, comptée une seule fois ; l'élevé reste mesuré.
    assert report["documented_hours"] == 5.0
    assert report["zones"]["trunk"]["projected_elevated_hours"] == 2.5
    assert report["tasks"] == []
    [declared] = report["analyses"][0]["declared"]
    assert declared["cycles_per_minute"] == 8.0
    assert declared["measured_cycles_per_minute"] == {"trunk": 3.0}


def test_declared_value_counts_even_when_the_video_is_not_representative():
    items = [_item("a", 4.0, representative=False,
                   recurrence=_recurrence(trunk={"cycles_per_minute": 3.0}))]

    report = project_bilan(9.0, items, [_task(zones=("trunk",), cpm=2.0, analysis_id="a")])

    assert report["zones"]["trunk"]["projected_cycles"] == 2 * 60 * 4
    assert report["warnings"] == []


def test_tasks_and_videos_together_cannot_exceed_the_workday():
    items = [_item("a", 6.0)]

    with pytest.raises(ValueError, match="dépassent la journée"):
        project_bilan(8.0, items, [_task(hours=3.0)])


def test_overlapping_time_slots_between_tasks_only_warn():
    tasks = [
        _task("t1", 2.0, slots=[{"start": "08:00", "end": "10:00"}], name="Peinture"),
        _task("t2", 2.0, slots=[{"start": "09:00", "end": "11:00"}], name="Saisie"),
        _task("t3", 1.0, slots=[{"start": "14:00", "end": "15:00"}], name="Rangement"),
    ]

    report = project_bilan(9.0, [], tasks)

    overlaps = [w for w in report["warnings"] if "chevauchent" in w]
    assert len(overlaps) == 1
    assert "Peinture" in overlaps[0] and "Saisie" in overlaps[0]


def test_task_without_zone_or_frequency_contributes_nothing_and_says_so():
    report = project_bilan(9.0, [], [_task(zones=(), cpm=None)])

    assert all(v["projected_cycles"] == 0.0 for v in report["zones"].values())
    assert any("non renseignées" in w for w in report["tasks"][0]["warnings"])
    assert any("aucune projection" in w for w in report["warnings"])


def test_slots_hours_sums_slots_and_rejects_bad_ones():
    from tms_vision.bilan import slots_hours

    assert slots_hours([{"start": "08:00", "end": "12:00"},
                        {"start": "13:30", "end": "17:00"}]) == 7.5
    with pytest.raises(ValueError):
        slots_hours([{"start": "10:00", "end": "09:00"}])
    with pytest.raises(ValueError):
        slots_hours([{"start": "8h", "end": "9h"}])
    with pytest.raises(ValueError, match="chevauchent"):
        slots_hours([{"start": "08:00", "end": "10:00"}, {"start": "09:00", "end": "11:00"}])
