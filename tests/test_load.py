import pytest

from tms_vision.load import MAX_LOAD_KG, Load, bounds, parse_load


def test_none_has_no_value_and_zero_bounds():
    load = parse_load("none")

    assert load == Load(kind="none", kg=None, kg_min=None, kg_max=None)
    assert bounds(load) == (0.0, 0.0)


def test_exact_load_bounds_are_the_value():
    load = parse_load("exact", kg=12.5)

    assert load.kg == 12.5
    assert bounds(load) == (12.5, 12.5)


def test_exact_zero_is_valid():
    assert bounds(parse_load("exact", kg=0)) == (0.0, 0.0)


def test_range_bounds_are_low_and_high():
    load = parse_load("range", kg_min=8, kg_max=12)

    assert (load.kg_min, load.kg_max) == (8.0, 12.0)
    assert bounds(load) == (8.0, 12.0)


def test_degenerate_range_is_accepted():
    assert bounds(parse_load("range", kg_min=5, kg_max=5)) == (5.0, 5.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": "none", "kg": 3},
        {"kind": "none", "kg_min": 1},
        {"kind": "exact"},
        {"kind": "exact", "kg": -1},
        {"kind": "exact", "kg": MAX_LOAD_KG + 0.1},
        {"kind": "exact", "kg": 5, "kg_min": 1},
        {"kind": "range", "kg_min": 8},
        {"kind": "range", "kg_max": 12},
        {"kind": "range", "kg_min": 12, "kg_max": 8},
        {"kind": "range", "kg_min": -1, "kg_max": 4},
        {"kind": "range", "kg_min": 1, "kg_max": MAX_LOAD_KG + 1},
        {"kind": "range", "kg": 5, "kg_min": 1, "kg_max": 9},
        {"kind": "unknown"},
    ],
)
def test_incoherent_loads_raise_value_error(kwargs):
    with pytest.raises(ValueError):
        parse_load(**kwargs)


def test_load_at_the_maximum_is_accepted():
    assert bounds(parse_load("exact", kg=MAX_LOAD_KG)) == (MAX_LOAD_KG, MAX_LOAD_KG)
