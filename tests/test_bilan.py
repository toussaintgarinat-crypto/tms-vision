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
