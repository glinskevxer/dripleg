"""Building a trap, a header and a reading without four screens of ceremony.

This started as a conftest under the diagnosis tests and moved here the first
time the loss tests wanted the same station. Shared builders in a conftest are
invisible to anything outside that directory, and the copy that gets made
instead drifts from the original inside a week.
"""

from __future__ import annotations

import datetime as dt

from dripleg.model.attributes import Accessibility, Criticality, ServiceType
from dripleg.model.catalogue import ConnectionType, TrapModel
from dripleg.model.header import DischargeDestination, SteamHeader
from dripleg.model.installation import TrapInstallation
from dripleg.model.operating import OperatingProfile
from dripleg.model.plant import Area
from dripleg.model.principles import OperatingPrinciple
from dripleg.model.tags import SiteCode, TrapTag
from dripleg.survey.condition import TrapCondition
from dripleg.survey.observation import Observation
from dripleg.survey.readings import (
    SightGlassView,
    SurveyMethod,
    TemperatureReading,
    UltrasonicReading,
)
from dripleg.units.money import Money
from dripleg.units.pressure import Pressure
from dripleg.units.temperature import Temperature

AREA = Area.of("WRX1", "B12", "Number 2 paper machine", "PM2")
TAG = TrapTag.parse("B12-MP-0043")
DAY = dt.date(2025, 4, 8)


def a_model(
    principle: OperatingPrinciple = OperatingPrinciple.THERMODYNAMIC_DISC,
    orifice: float = 0.093,
) -> TrapModel:
    return TrapModel(
        manufacturer="Halden",
        code="TD52",
        principle=principle,
        orifice_diameter_in=orifice,
        max_operating_pressure=Pressure.from_psig(600.0),
        max_back_pressure_percent=80.0,
        connection_size_in=0.5,
        connection_type=ConnectionType.SCREWED,
        list_price=Money.from_dollars("184.00"),
    )


def a_header(
    operating: float = 125.0,
    discharge: float = 15.0,
    destination: DischargeDestination = DischargeDestination.RETURN_LINE,
) -> SteamHeader:
    return SteamHeader.of(
        AREA,
        "MP",
        "Machine room main",
        operating,
        discharge_psig=discharge,
        destination=destination,
    )


def header_for(tag: TrapTag) -> SteamHeader:
    """The header a tag implies, so a station can be built from a tag alone."""

    area = Area.of("WRX1", tag.area.value, f"Area {tag.area}", "PM2")
    return SteamHeader.of(area, tag.system.value, f"{tag.system} main", 125.0, discharge_psig=15.0)


def a_station(**overrides: object) -> TrapInstallation:
    tag = overrides.get("tag", TAG)
    assert isinstance(tag, TrapTag)
    fields: dict[str, object] = {
        "site": SiteCode("WRX1"),
        "tag": TAG,
        "header": header_for(tag),
        "model": a_model(),
        "service": ServiceType.DRIP,
        "accessibility": Accessibility.GROUND_LEVEL,
        "criticality": Criticality.NUISANCE,
        "profile": OperatingProfile.continuous(),
        "installed_on": dt.date(2021, 6, 14),
    }
    fields.update(overrides)
    return TrapInstallation(**fields)  # type: ignore[arg-type]


def probe(decibels: float, cycles: int | None = None, seconds: float = 30.0) -> UltrasonicReading:
    return UltrasonicReading(decibels=decibels, seconds=seconds, cycles=cycles)


def pipe(
    upstream: float,
    downstream: float,
    ambient: float | None = None,
    method: SurveyMethod = SurveyMethod.CONTACT_TEMPERATURE,
) -> TemperatureReading:
    return TemperatureReading(
        upstream=Temperature.from_fahrenheit(upstream),
        downstream=Temperature.from_fahrenheit(downstream),
        ambient=None if ambient is None else Temperature.from_fahrenheit(ambient),
        method=method,
    )


def a_reading(**overrides: object) -> Observation:
    fields: dict[str, object] = {
        "tag": TAG,
        "observed_on": DAY,
        "technician": "R Ellis",
        "reported_condition": TrapCondition.OK,
    }
    fields.update(overrides)
    return Observation(**fields)  # type: ignore[arg-type]


__all__ = [
    "AREA",
    "DAY",
    "TAG",
    "SightGlassView",
    "a_header",
    "a_model",
    "header_for",
    "a_reading",
    "a_station",
    "pipe",
    "probe",
]
