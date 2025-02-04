from __future__ import annotations

import pytest

from dripleg.errors import ValidationError
from dripleg.model.header import DischargeDestination, PressureClass, SteamHeader
from dripleg.model.plant import Area
from dripleg.units.pressure import Pressure


def area() -> Area:
    return Area.of("WRX1", "B12", "Number 2 paper machine", "PM2")


def test_pressure_classes_fall_where_the_schedule_puts_them() -> None:
    assert PressureClass.of(Pressure.from_psig(200.0)) is PressureClass.HIGH
    assert PressureClass.of(Pressure.from_psig(150.0)) is PressureClass.HIGH
    assert PressureClass.of(Pressure.from_psig(60.0)) is PressureClass.MEDIUM
    assert PressureClass.of(Pressure.from_psig(16.0)) is PressureClass.MEDIUM
    assert PressureClass.of(Pressure.from_psig(15.0)) is PressureClass.LOW
    assert PressureClass.of(Pressure.from_inches_mercury_vacuum(10.0)) is PressureClass.VACUUM


def test_pressure_classes_print_the_way_the_plant_says_them() -> None:
    assert PressureClass.HIGH.label == "HP"
    assert PressureClass.LOW.label == "LP"
    assert PressureClass.VACUUM.label == "vacuum"


def test_a_header_knows_its_class_and_its_saturation_temperature() -> None:
    header = SteamHeader.of(area(), "MP", "Machine room main", 125.0)
    assert header.pressure_class is PressureClass.MEDIUM
    assert header.saturation_temperature.fahrenheit == pytest.approx(353.0, abs=1.0)


def test_a_header_defaults_its_design_pressure_above_its_operating_pressure() -> None:
    header = SteamHeader.of(area(), "MP", "Main", 125.0)
    assert header.design_pressure.psig == pytest.approx(150.0)


def test_a_header_cannot_run_above_its_design_pressure() -> None:
    with pytest.raises(ValidationError, match="above its design pressure"):
        SteamHeader.of(area(), "MP", "Main", 125.0, design_psig=100.0)


def test_the_discharge_cannot_be_above_the_steam() -> None:
    with pytest.raises(ValidationError, match="backwards"):
        SteamHeader.of(area(), "LP", "Main", 15.0, discharge_psig=30.0)


def test_a_header_needs_a_name() -> None:
    with pytest.raises(ValidationError, match="needs a name"):
        SteamHeader.of(area(), "MP", "   ", 125.0)


def test_the_differential_is_what_the_trap_pushes_against() -> None:
    header = SteamHeader.of(area(), "MP", "Main", 125.0, discharge_psig=15.0)
    assert header.differential_pressure.psia == pytest.approx(110.0)


def test_the_back_pressure_ratio_is_absolute_over_absolute() -> None:
    header = SteamHeader.of(area(), "MP", "Main", 125.0, discharge_psig=15.0)
    assert header.back_pressure_ratio == pytest.approx(29.696 / 139.696, abs=0.001)


def test_a_normal_return_line_leaves_the_seat_choked() -> None:
    assert SteamHeader.of(area(), "MP", "Main", 125.0, discharge_psig=15.0).discharge_is_choked


def test_a_high_return_pressure_unchokes_the_seat() -> None:
    header = SteamHeader.of(area(), "LP", "Main", 30.0, discharge_psig=25.0)
    assert not header.discharge_is_choked


def test_condensate_is_only_recovered_from_some_destinations() -> None:
    assert DischargeDestination.RETURN_LINE.condensate_is_recovered
    assert DischargeDestination.FLASH_VESSEL.condensate_is_recovered
    assert not DischargeDestination.ATMOSPHERE.condensate_is_recovered
    assert not DischargeDestination.DRAIN.condensate_is_recovered


def test_only_an_open_discharge_shows_itself() -> None:
    assert DischargeDestination.ATMOSPHERE.steam_is_visible
    assert not DischargeDestination.RETURN_LINE.steam_is_visible


def test_a_trap_venting_to_air_is_not_venting_into_a_vacuum() -> None:
    with pytest.raises(ValidationError, match="into a vacuum"):
        SteamHeader(
            site=area().site,
            area=area().code,
            system=SteamHeader.of(area(), "LP", "Main", 15.0).system,
            name="Main",
            operating_pressure=Pressure.from_psig(15.0),
            design_pressure=Pressure.from_psig(50.0),
            discharge_pressure=Pressure.from_inches_mercury_vacuum(5.0),
            destination=DischargeDestination.ATMOSPHERE,
        )


def test_the_header_key_is_site_area_and_system() -> None:
    assert SteamHeader.of(area(), "MP", "Main", 125.0).key == ("WRX1", "B12", "MP")


def test_printing_a_header() -> None:
    header = SteamHeader.of(area(), "MP", "Machine room main", 125.0)
    assert str(header) == "B12-MP Machine room main at 125.0 psig"
