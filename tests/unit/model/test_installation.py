from __future__ import annotations

import datetime as dt

import pytest

from dripleg.errors import ValidationError
from dripleg.model.attributes import Accessibility, Criticality, ServiceType
from dripleg.model.catalogue import ConnectionType, TrapModel
from dripleg.model.header import DischargeDestination, SteamHeader
from dripleg.model.installation import TrapInstallation
from dripleg.model.operating import OperatingProfile
from dripleg.model.plant import Area
from dripleg.model.principles import OperatingPrinciple
from dripleg.model.tags import SiteCode, TrapTag
from dripleg.units.money import Money
from dripleg.units.pressure import Pressure

AREA = Area.of("WRX1", "B12", "Number 2 paper machine", "PM2")


def a_model(code: str = "TD52", pmo_psig: float = 600.0) -> TrapModel:
    return TrapModel(
        manufacturer="Halden",
        code=code,
        principle=OperatingPrinciple.THERMODYNAMIC_DISC,
        orifice_diameter_in=0.093,
        max_operating_pressure=Pressure.from_psig(pmo_psig),
        max_back_pressure_percent=80.0,
        connection_size_in=0.5,
        connection_type=ConnectionType.SCREWED,
        list_price=Money.from_dollars("184.00"),
    )


def a_header(destination: DischargeDestination = DischargeDestination.RETURN_LINE) -> SteamHeader:
    return SteamHeader.of(
        AREA, "MP", "Machine room main", 125.0, discharge_psig=15.0, destination=destination
    )


def an_installation(**overrides: object) -> TrapInstallation:
    base: dict[str, object] = {
        "site": SiteCode("WRX1"),
        "tag": TrapTag.parse("B12-MP-0043"),
        "header": a_header(),
        "model": a_model(),
        "service": ServiceType.DRIP,
        "accessibility": Accessibility.GROUND_LEVEL,
        "criticality": Criticality.NUISANCE,
        "profile": OperatingProfile.continuous(),
        "installed_on": dt.date(2021, 6, 14),
    }
    base.update(overrides)
    return TrapInstallation(**base)  # type: ignore[arg-type]


def test_an_installation_keys_on_site_and_tag() -> None:
    assert an_installation().key == ("WRX1", "B12-MP-0043")


def test_the_tag_area_has_to_match_the_header_area() -> None:
    with pytest.raises(ValidationError, match="same area"):
        an_installation(tag=TrapTag.parse("C3-MP-0001"))


def test_a_trap_and_its_header_are_at_the_same_site() -> None:
    with pytest.raises(ValidationError, match="different sites"):
        an_installation(site=SiteCode("WRX2"))


def test_a_model_that_cannot_take_the_header_pressure_is_refused() -> None:
    with pytest.raises(ValidationError, match="rated to"):
        an_installation(model=a_model(pmo_psig=60.0))


def test_a_trap_cannot_come_out_before_it_went_in() -> None:
    with pytest.raises(ValidationError, match="before it went in"):
        an_installation(removed_on=dt.date(2020, 1, 1))


def test_a_station_has_at_most_two_isolation_valves() -> None:
    with pytest.raises(ValidationError, match="isolation valves"):
        an_installation(isolation_valves=3)
    assert an_installation(isolation_valves=0).isolation_valves == 0


def test_an_interval_override_has_to_be_sane() -> None:
    with pytest.raises(ValidationError, match="one month to five years"):
        an_installation(interval_months_override=0)
    with pytest.raises(ValidationError, match="one month to five years"):
        an_installation(interval_months_override=120)


def test_the_station_destination_falls_back_to_the_header() -> None:
    assert an_installation().discharge_destination is DischargeDestination.RETURN_LINE
    vented = an_installation(destination=DischargeDestination.ATMOSPHERE)
    assert vented.discharge_destination is DischargeDestination.ATMOSPHERE
    assert not vented.loss_is_recovered
    assert an_installation().loss_is_recovered


def test_in_service_is_half_open_on_the_removal_day() -> None:
    trap = an_installation(removed_on=dt.date(2024, 3, 1))
    assert not trap.is_in_service_on(dt.date(2021, 6, 13))
    assert trap.is_in_service_on(dt.date(2021, 6, 14))
    assert trap.is_in_service_on(dt.date(2024, 2, 29))
    assert not trap.is_in_service_on(dt.date(2024, 3, 1))
    assert trap.is_removed


def test_a_trap_still_in_service_has_no_end() -> None:
    trap = an_installation()
    assert not trap.is_removed
    assert trap.is_in_service_on(dt.date(2030, 1, 1))


def test_age_stops_counting_on_the_day_it_came_out() -> None:
    trap = an_installation(removed_on=dt.date(2021, 7, 14))
    assert trap.age_days_on(dt.date(2021, 6, 24)) == 10
    assert trap.age_days_on(dt.date(2025, 1, 1)) == 30
    with pytest.raises(ValidationError, match="before the trap went in"):
        trap.age_days_on(dt.date(2020, 1, 1))


def test_the_survey_interval_comes_from_the_service_unless_overridden() -> None:
    assert an_installation().survey_interval_months == 12
    assert an_installation(service=ServiceType.TRACER).survey_interval_months == 24
    assert an_installation(interval_months_override=3).survey_interval_months == 3


def test_the_next_due_date_is_the_interval_out() -> None:
    trap = an_installation(service=ServiceType.TURBINE_DRAIN)
    assert trap.next_due_after(dt.date(2025, 3, 31)) == dt.date(2025, 9, 30)


def test_a_trap_can_be_isolated_only_with_a_valve_and_running_access() -> None:
    assert an_installation().can_be_isolated
    assert not an_installation(isolation_valves=0).can_be_isolated
    assert not an_installation(accessibility=Accessibility.SHUTDOWN_ONLY).can_be_isolated


def test_replacing_the_trap_keeps_the_station() -> None:
    trap = an_installation()
    swapped = trap.replaced_with(a_model("TD75"), dt.date(2025, 4, 2))
    assert swapped.tag == trap.tag
    assert swapped.model.code == "TD75"
    assert swapped.installed_on == dt.date(2025, 4, 2)
    assert swapped.service is trap.service


def test_a_replacement_cannot_predate_what_it_replaces() -> None:
    with pytest.raises(ValidationError, match="cannot predate"):
        an_installation().replaced_with(a_model("TD75"), dt.date(2019, 1, 1))


def test_a_retired_station_takes_no_more_traps() -> None:
    retired = an_installation().retired_on(dt.date(2025, 5, 1))
    assert retired.removed_on == dt.date(2025, 5, 1)
    with pytest.raises(ValidationError, match="out of service"):
        retired.replaced_with(a_model("TD75"), dt.date(2025, 6, 1))
    with pytest.raises(ValidationError, match="already out of service"):
        retired.retired_on(dt.date(2025, 6, 1))


def test_printing_an_installation() -> None:
    assert str(an_installation()) == "B12-MP-0043 drip on Machine room main"


def test_a_station_without_geometry_cannot_be_sized() -> None:
    assert not an_installation().has_geometry


def test_a_station_with_a_pipe_and_a_run_can_be_sized() -> None:
    station = an_installation(pipe_nominal="4", run_length_ft=180.0)
    assert station.has_geometry
    assert station.run_length_ft == 180.0
    assert station.warmup_minutes == 30.0


def test_half_the_geometry_is_refused() -> None:
    with pytest.raises(ValidationError, match="both a pipe size and a run length"):
        an_installation(pipe_nominal="4")
    with pytest.raises(ValidationError, match="both a pipe size and a run length"):
        an_installation(run_length_ft=180.0)


def test_a_run_of_no_length_is_refused() -> None:
    with pytest.raises(ValidationError, match="has a length"):
        an_installation(pipe_nominal="4", run_length_ft=0.0)


def test_a_warm_up_of_no_time_is_refused() -> None:
    with pytest.raises(ValidationError, match="takes some time"):
        an_installation(warmup_minutes=0.0)


def test_a_refit_carries_the_geometry_across() -> None:
    station = an_installation(pipe_nominal="4", run_length_ft=180.0, warmup_minutes=45.0)
    swapped = station.replaced_with(a_model("TD75"), dt.date(2025, 4, 2))
    assert swapped.pipe_nominal == "4"
    assert swapped.run_length_ft == 180.0
    assert swapped.warmup_minutes == 45.0
