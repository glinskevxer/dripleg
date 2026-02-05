from __future__ import annotations

import datetime as dt

import pytest

from dripleg.errors import ValidationError
from dripleg.loss.accrual import accrue, accrue_all
from dripleg.model.operating import OperatingProfile, ServicePattern
from dripleg.model.tags import TrapTag
from dripleg.units.money import Money
from tests.support.build import a_station

FOUND = dt.date(2025, 4, 8)
ANNUAL = Money.from_dollars("2600.00")


def an_accrual(as_at: dt.date, **station: object):  # type: ignore[no-untyped-def]
    return accrue(
        a_station(**station),
        found_on=FOUND,
        as_at=as_at,
        annual_cost=ANNUAL,
        pounds_per_hour=48.0,
    )


def test_nothing_has_accrued_on_the_day_it_was_found() -> None:
    accrual = an_accrual(FOUND)
    assert accrual.days == 0
    assert accrual.live_hours == pytest.approx(24.0)
    assert accrual.cost.cents < 800


def test_a_year_of_a_continuous_leg_accrues_the_annual_cost() -> None:
    accrual = an_accrual(FOUND + dt.timedelta(days=364))
    assert accrual.share_of_a_year == pytest.approx(1.0, abs=0.01)
    assert accrual.cost.cents == pytest.approx(ANNUAL.cents, rel=0.01)


def test_half_a_year_accrues_about_half() -> None:
    accrual = an_accrual(FOUND + dt.timedelta(days=181))
    assert accrual.cost.cents == pytest.approx(ANNUAL.cents / 2, rel=0.02)


def test_a_seasonal_leg_accrues_nothing_over_the_summer() -> None:
    heating = OperatingProfile("HEAT", "Heating", ServicePattern.HEATING_SEASON)
    summer = accrue(
        a_station(profile=heating),
        found_on=dt.date(2025, 5, 1),
        as_at=dt.date(2025, 8, 31),
        annual_cost=ANNUAL,
        pounds_per_hour=48.0,
    )
    assert summer.live_hours == 0.0
    assert summer.cost.is_zero
    assert not summer.is_material


def test_a_seasonal_leg_accrues_over_the_winter() -> None:
    heating = OperatingProfile("HEAT", "Heating", ServicePattern.HEATING_SEASON)
    winter = accrue(
        a_station(profile=heating),
        found_on=dt.date(2025, 11, 1),
        as_at=dt.date(2026, 2, 28),
        annual_cost=ANNUAL,
        pounds_per_hour=48.0,
    )
    assert winter.live_hours > 2500.0
    assert winter.cost.cents > 0
    assert winter.is_material


def test_a_load_factor_slows_the_accrual() -> None:
    tracer = OperatingProfile("TRC", "Tracer", load_factor=0.25)
    slow = an_accrual(FOUND + dt.timedelta(days=100), profile=tracer)
    quick = an_accrual(FOUND + dt.timedelta(days=100))
    assert slow.live_hours == pytest.approx(quick.live_hours * 0.25)
    assert slow.share_of_a_year == pytest.approx(quick.share_of_a_year)


def test_the_steam_accrues_with_the_money() -> None:
    accrual = an_accrual(FOUND + dt.timedelta(days=99))
    assert accrual.steam.pounds == pytest.approx(48.0 * accrual.live_hours)


def test_accruing_before_the_finding_is_refused() -> None:
    with pytest.raises(ValidationError, match="before it was found"):
        an_accrual(FOUND - dt.timedelta(days=1))


def test_a_backlog_accrues_dearest_first() -> None:
    station = a_station(tag=TrapTag.parse("B12-MP-1"))
    other = a_station(tag=TrapTag.parse("B12-MP-2"))
    accruals = accrue_all(
        [
            (station, FOUND, Money.from_dollars("500.00"), 10.0),
            (other, FOUND, Money.from_dollars("2600.00"), 48.0),
        ],
        as_at=FOUND + dt.timedelta(days=100),
    )
    assert [str(a.tag) for a in accruals] == ["B12-MP-0002", "B12-MP-0001"]


def test_a_backlog_leaves_out_anything_found_after_the_day() -> None:
    station = a_station()
    accruals = accrue_all(
        [(station, FOUND + dt.timedelta(days=30), ANNUAL, 48.0)],
        as_at=FOUND,
    )
    assert accruals == []


def test_an_empty_backlog_accrues_nothing() -> None:
    assert accrue_all([], as_at=FOUND) == []


def test_printing_an_accrual() -> None:
    printed = str(an_accrual(FOUND + dt.timedelta(days=100)))
    assert printed.startswith("B12-MP-0043 has cost $")
    assert "in the 100 days since 2025-04-08" in printed
