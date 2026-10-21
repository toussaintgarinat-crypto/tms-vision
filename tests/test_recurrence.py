import json

import pytest

from tms_vision.capsules import ZONES
from tms_vision.recurrence import ZONE_ANGLE_COLUMN, compute_recurrence, load_thresholds


def _thresholds(calibrated=False, **overrides):
    zone_thresholds = {
        "min_prominence_deg": 10.0,
        "static_variation_deg": 15.0,
        "repetitive_cycles_per_minute": None,
        "static_seconds": None,
    }
    zones = {zone: dict(zone_thresholds) for zone in ZONES}
    for zone, values in overrides.items():
        zones[zone].update(values)
    return {"calibrated": calibrated, "zones": zones}


def _frame(index, timestamp, detected=True, **values):
    row = {
        "frame_index": index,
        "timestamp_seconds": timestamp,
        "detected": detected,
        "neck_flexion_deg": None,
        "trunk_flexion_deg": None,
        "upper_arm_flexion_deg": None,
        "lower_arm_angle_deg": None,
        "neck_segment_action_level": None,
        "trunk_segment_action_level": None,
        "upper_arm_segment_action_level": None,
        "lower_arm_segment_action_level": None,
    }
    row.update(values)
    return row


def _sawtooth_trunk_frames():
    # Angle du tronc alternant 0 / 20 degres toutes les 10 s sur 60 s :
    # 5 changements de direction -> 2.5 cycles.
    return [
        _frame(i, i * 10.0, trunk_flexion_deg=0.0 if i % 2 == 0 else 20.0)
        for i in range(7)
    ]


def test_zone_angle_column_covers_every_zone():
    assert set(ZONE_ANGLE_COLUMN) == set(ZONES)


def test_sawtooth_series_yields_cycles_rate_and_mean_cycle_duration():
    result = compute_recurrence(_sawtooth_trunk_frames(), _thresholds())

    trunk = result["zones"]["trunk"]
    assert result["sample_seconds"] == 60.0
    assert trunk["cycles"] == 2.5
    assert trunk["cycles_per_minute"] == 2.5
    assert trunk["mean_cycle_seconds"] == 24.0


def test_constant_series_has_no_cycle_and_is_fully_static():
    frames = [_frame(i, float(i), trunk_flexion_deg=30.0) for i in range(11)]

    trunk = compute_recurrence(frames, _thresholds())["zones"]["trunk"]

    assert trunk["cycles"] == 0.0
    assert trunk["cycles_per_minute"] == 0.0
    assert trunk["mean_cycle_seconds"] is None
    assert trunk["longest_static_seconds"] == 10.0


def test_zone_without_any_angle_has_zero_indicators():
    neck = compute_recurrence(_sawtooth_trunk_frames(), _thresholds())["zones"]["neck"]

    assert neck["cycles"] == 0.0
    assert neck["mean_cycle_seconds"] is None
    assert neck["longest_static_seconds"] == 0.0
    assert neck["elevated_seconds"] == 0.0


def test_undetected_frames_are_ignored_for_angles_but_count_in_sample_duration():
    frames = _sawtooth_trunk_frames()
    frames[3] = _frame(3, 30.0, detected=False, trunk_flexion_deg=999.0)

    result = compute_recurrence(frames, _thresholds())

    assert result["sample_seconds"] == 60.0
    # 999 ne doit jamais apparaitre comme une amplitude de cycle : sans la frame 3,
    # la serie est 0/20/0/0/20/0 (3 changements de direction), pas un saut vers 999.
    assert result["zones"]["trunk"]["cycles"] == 1.5


def test_elevated_seconds_accumulates_time_in_elevated_levels_per_zone():
    frames = [
        _frame(0, 0.0, trunk_segment_action_level="changement_immediat"),
        _frame(1, 2.0, trunk_segment_action_level="investigation_recommandee"),
        _frame(2, 5.0, trunk_segment_action_level="investigation_et_changement_bientot"),
        _frame(3, 6.0, trunk_segment_action_level="acceptable"),
    ]

    trunk = compute_recurrence(frames, _thresholds())["zones"]["trunk"]

    # frame 0 : 2 s ; frame 2 : 1 s ; investigation_recommandee ne compte pas.
    assert trunk["elevated_seconds"] == 3.0


def test_empty_frames_give_zero_sample_and_no_rate():
    result = compute_recurrence([], _thresholds())

    assert result["sample_seconds"] == 0.0
    assert result["zones"]["trunk"]["cycles_per_minute"] is None


def test_single_frame_sample_lasts_one_second():
    result = compute_recurrence([_frame(0, 5.0, trunk_flexion_deg=10.0)], _thresholds())

    assert result["sample_seconds"] == 1.0


def test_assessment_is_none_while_interpretation_thresholds_are_empty():
    result = compute_recurrence(_sawtooth_trunk_frames(), _thresholds())

    assert all(zone["assessment"] is None for zone in result["zones"].values())
    assert result["thresholds_calibrated"] is False


def test_assessment_compares_rate_to_zone_threshold():
    frames = _sawtooth_trunk_frames()  # 2.5 cycles par minute

    repetitive = compute_recurrence(
        frames, _thresholds(trunk={"repetitive_cycles_per_minute": 2.0})
    )["zones"]["trunk"]
    not_repetitive = compute_recurrence(
        frames, _thresholds(trunk={"repetitive_cycles_per_minute": 4.0})
    )["zones"]["trunk"]

    assert repetitive["assessment"] == "repetitive"
    assert not_repetitive["assessment"] == "not_repetitive"


def test_min_prominence_is_calibrated_per_zone():
    # Oscillation de 8 degres : ignoree a 10, comptee a 5 (seulement pour le tronc).
    frames = [
        _frame(i, float(i), trunk_flexion_deg=0.0 if i % 2 == 0 else 8.0,
               neck_flexion_deg=0.0 if i % 2 == 0 else 8.0)
        for i in range(10)
    ]

    result = compute_recurrence(frames, _thresholds(trunk={"min_prominence_deg": 5.0}))

    assert result["zones"]["trunk"]["cycles"] > 0
    assert result["zones"]["neck"]["cycles"] == 0.0


def test_static_variation_is_calibrated_per_zone():
    frames = [_frame(i, float(i), trunk_flexion_deg=i * 4.0, neck_flexion_deg=i * 4.0)
              for i in range(6)]  # 0 -> 20 degres de variation totale

    result = compute_recurrence(frames, _thresholds(trunk={"static_variation_deg": 25.0}))

    assert result["zones"]["trunk"]["longest_static_seconds"] == 5.0
    assert result["zones"]["neck"]["longest_static_seconds"] < 5.0


def test_thresholds_calibrated_flag_is_read_from_thresholds():
    result = compute_recurrence(_sawtooth_trunk_frames(), _thresholds(calibrated=True))

    assert result["thresholds_calibrated"] is True


def test_shipped_thresholds_file_is_uncalibrated_with_poc_starting_values():
    thresholds = load_thresholds()

    assert thresholds["calibrated"] is False
    assert set(thresholds["zones"]) == set(ZONES)
    for zone in ZONES:
        assert thresholds["zones"][zone] == {
            "min_prominence_deg": 10.0,
            "static_variation_deg": 15.0,
            "repetitive_cycles_per_minute": None,
            "static_seconds": None,
        }


def test_load_thresholds_rejects_a_file_missing_a_zone(tmp_path):
    path = tmp_path / "thresholds.json"
    path.write_text(json.dumps({"calibrated": False, "zones": {"neck": {}}}))

    with pytest.raises(ValueError):
        load_thresholds(path)
