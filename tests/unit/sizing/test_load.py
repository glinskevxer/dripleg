from __future__ import annotations

import pytest

from dripleg.errors import OutOfRangeError, ValidationError
from dripleg.sizing.load import (
    BARE_PIPE_COEFFICIENT,
    PIPE_SIZES,
    STEEL_SPECIFIC_HEAT,
    PipeSize,
    pipe_size,
    running_load,
    warmup_load,
)
from dripleg.units.pressure import Pressure
from dripleg.units.temperature import Temperature

HEADER = Pressure.from_psig(125.0)
COLD = Temperature.from_fahrenheit(60.0)
PLANT = Temperature.from_fahrenheit(75.0)


def test_the_pipe_table_climbs_with_size() -> None:
    diameters = [p.outside_diameter_in for p in PIPE_SIZES.values()]
    weights = [p.weight_lb_per_ft for p in PIPE_SIZES.values()]
    assert diameters == sorted(diameters)
    assert weights == sorted(weights)


def test_the_surface_area_is_the_circumference() -> None:
    four_inch = PIPE_SIZES["4"]
    assert four_inch.surface_ft2_per_ft == pytest.approx(1.178, abs=0.005)


def test_a_pipe_size_is_looked_up_loosely() -> None:
    assert pipe_size(" 1-1/4 ") is PIPE_SIZES["1-1/4"]
    assert pipe_size('6"') is PIPE_SIZES["6"]


def test_a_pipe_size_nobody_stocks() -> None:
    with pytest.raises(ValidationError, match="not a pipe size"):
        pipe_size("5")


def test_a_pipe_needs_a_diameter_and_a_weight() -> None:
    with pytest.raises(ValidationError, match="diameter and a weight"):
        PipeSize("bad", 0.0, 1.0)
    with pytest.raises(ValidationError, match="diameter and a weight"):
        PipeSize("bad", 1.0, 0.0)


def test_the_warm_up_load_is_the_steel_being_heated() -> None:
    pipe = PIPE_SIZES["4"]
    load = warmup_load(pipe, 100.0, HEADER, COLD, minutes=30.0, safety_factor=1.0)
    steel = pipe.weight_lb_per_ft * 100.0
    rise = 353.0 - 60.0
    expected = steel * STEEL_SPECIFIC_HEAT * rise / 868.0 * 2.0
    assert load.pounds_per_hour == pytest.approx(expected, rel=0.02)


def test_the_safety_factor_multiplies_the_warm_up_load() -> None:
    pipe = PIPE_SIZES["4"]
    plain = warmup_load(pipe, 100.0, HEADER, COLD, safety_factor=1.0)
    doubled = warmup_load(pipe, 100.0, HEADER, COLD, safety_factor=2.0)
    assert doubled.pounds_per_hour == pytest.approx(2 * plain.pounds_per_hour)


def test_a_longer_warm_up_makes_a_smaller_load() -> None:
    pipe = PIPE_SIZES["4"]
    quick = warmup_load(pipe, 100.0, HEADER, COLD, minutes=15.0)
    slow = warmup_load(pipe, 100.0, HEADER, COLD, minutes=60.0)
    assert quick.pounds_per_hour == pytest.approx(4 * slow.pounds_per_hour)


def test_a_bigger_pipe_makes_a_bigger_warm_up_load() -> None:
    small = warmup_load(PIPE_SIZES["2"], 100.0, HEADER, COLD)
    big = warmup_load(PIPE_SIZES["8"], 100.0, HEADER, COLD)
    assert big.pounds_per_hour > 5 * small.pounds_per_hour


def test_a_warm_up_with_no_time_or_a_daft_factor_is_refused() -> None:
    with pytest.raises(ValidationError, match="takes some time"):
        warmup_load(PIPE_SIZES["4"], 100.0, HEADER, COLD, minutes=0.0)
    with pytest.raises(ValidationError, match="at least one"):
        warmup_load(PIPE_SIZES["4"], 100.0, HEADER, COLD, safety_factor=0.5)


def test_a_run_of_no_length_is_refused() -> None:
    with pytest.raises(ValidationError, match="has a length"):
        warmup_load(PIPE_SIZES["4"], 0.0, HEADER, COLD)
    with pytest.raises(ValidationError, match="has a length"):
        running_load(PIPE_SIZES["4"], 0.0, HEADER, COLD)


def test_air_hotter_than_the_steam_is_refused() -> None:
    hot = Temperature.from_fahrenheit(400.0)
    with pytest.raises(OutOfRangeError, match="nothing condenses"):
        warmup_load(PIPE_SIZES["4"], 100.0, HEADER, hot)
    with pytest.raises(OutOfRangeError, match="nothing condenses"):
        running_load(PIPE_SIZES["4"], 100.0, HEADER, hot)


def test_the_running_load_is_the_lagging_leaking() -> None:
    pipe = PIPE_SIZES["4"]
    load = running_load(pipe, 100.0, HEADER, PLANT, insulated=False)
    area = pipe.surface_ft2_per_ft * 100.0
    expected = area * BARE_PIPE_COEFFICIENT * (353.0 - 75.0) / 868.0
    assert load.pounds_per_hour == pytest.approx(expected, rel=0.02)


def test_insulation_cuts_the_running_load_a_long_way() -> None:
    bare = running_load(PIPE_SIZES["4"], 100.0, HEADER, PLANT, insulated=False)
    lagged = running_load(PIPE_SIZES["4"], 100.0, HEADER, PLANT)
    assert lagged.pounds_per_hour == pytest.approx(bare.pounds_per_hour * 0.15, rel=0.01)


def test_worse_lagging_lets_more_through() -> None:
    good = running_load(PIPE_SIZES["4"], 100.0, HEADER, PLANT, insulation_efficiency=0.9)
    poor = running_load(PIPE_SIZES["4"], 100.0, HEADER, PLANT, insulation_efficiency=0.5)
    assert poor.pounds_per_hour > good.pounds_per_hour


def test_an_insulation_efficiency_outside_the_range_is_refused() -> None:
    for bad in (-0.1, 1.0, 1.5):
        with pytest.raises(ValidationError, match="insulation efficiency"):
            running_load(PIPE_SIZES["4"], 100.0, HEADER, PLANT, insulation_efficiency=bad)


def test_the_warm_up_load_dwarfs_the_running_load() -> None:
    warm = warmup_load(PIPE_SIZES["6"], 200.0, HEADER, COLD)
    running = running_load(PIPE_SIZES["6"], 200.0, HEADER, PLANT)
    assert warm.pounds_per_hour > 10 * running.pounds_per_hour


def test_a_lower_pressure_makes_less_condensate() -> None:
    low = running_load(PIPE_SIZES["4"], 100.0, Pressure.from_psig(15.0), PLANT)
    high = running_load(PIPE_SIZES["4"], 100.0, Pressure.from_psig(250.0), PLANT)
    assert high.pounds_per_hour > low.pounds_per_hour
