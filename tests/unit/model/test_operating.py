from __future__ import annotations

import datetime as dt

import pytest

from dripleg.errors import ValidationError
from dripleg.model.calendar import DateRange
from dripleg.model.operating import OperatingProfile, ServicePattern


def test_a_continuous_line_runs_the_whole_year() -> None:
    profile = OperatingProfile.continuous()
    assert profile.annual_hours() == pytest.approx(8760.0)
    assert all(profile.is_live_in(m) for m in range(1, 13))


def test_a_heating_season_line_stops_in_the_summer() -> None:
    profile = OperatingProfile("HEAT", "Building heating", ServicePattern.HEATING_SEASON)
    assert profile.is_live_in(1)
    assert not profile.is_live_in(7)
    assert profile.annual_hours() == pytest.approx(8760.0 * 7 / 12)


def test_a_cooling_season_line_is_the_other_half() -> None:
    profile = OperatingProfile("COOL", "Absorption chiller", ServicePattern.COOLING_SEASON)
    assert profile.is_live_in(7)
    assert not profile.is_live_in(1)
    assert profile.annual_hours() == pytest.approx(8760.0 * 5 / 12)


def test_a_load_factor_cuts_the_hours() -> None:
    profile = OperatingProfile("TRC", "Freeze protection tracer", load_factor=0.35)
    assert profile.annual_hours() == pytest.approx(8760.0 * 0.35)


def test_a_load_factor_has_to_be_a_fraction() -> None:
    for bad in (0.0, -0.2, 1.5):
        with pytest.raises(ValidationError, match="load factor"):
            OperatingProfile("X", "X", load_factor=bad)


def test_a_profile_needs_a_code_and_a_name() -> None:
    with pytest.raises(ValidationError, match="needs a code"):
        OperatingProfile("  ", "Continuous")
    with pytest.raises(ValidationError, match="needs a name"):
        OperatingProfile("CONT", " ")


def test_a_campaign_carries_its_own_months() -> None:
    profile = OperatingProfile(
        "CAMP",
        "Beet campaign",
        ServicePattern.CAMPAIGN,
        campaign_months=frozenset({9, 10, 11, 12, 1}),
    )
    assert profile.is_live_in(10)
    assert not profile.is_live_in(6)
    assert profile.annual_hours() == pytest.approx(8760.0 * 5 / 12)


def test_a_campaign_without_months_is_refused() -> None:
    with pytest.raises(ValidationError, match="which months"):
        OperatingProfile("CAMP", "Beet", ServicePattern.CAMPAIGN)
    with pytest.raises(ValidationError, match="month numbers"):
        OperatingProfile("CAMP", "Beet", ServicePattern.CAMPAIGN, campaign_months=frozenset({13}))


def test_only_a_campaign_carries_months() -> None:
    with pytest.raises(ValidationError, match="only a campaign"):
        OperatingProfile("CONT", "Continuous", campaign_months=frozenset({1}))


def test_a_month_number_is_checked() -> None:
    with pytest.raises(ValidationError, match="not a month number"):
        OperatingProfile.continuous().is_live_in(0)


def test_seasonal_patterns_know_they_are_seasonal() -> None:
    assert ServicePattern.HEATING_SEASON.is_seasonal
    assert ServicePattern.CAMPAIGN.is_seasonal
    assert not ServicePattern.CONTINUOUS.is_seasonal
    assert not ServicePattern.INTERMITTENT.is_seasonal


def test_hours_in_a_window_count_the_days() -> None:
    profile = OperatingProfile.continuous()
    january = DateRange(dt.date(2025, 1, 1), dt.date(2025, 2, 1))
    assert profile.hours_in(january) == pytest.approx(31 * 24.0)


def test_hours_in_a_window_that_straddles_the_end_of_the_season() -> None:
    profile = OperatingProfile("HEAT", "Building heating", ServicePattern.HEATING_SEASON)
    window = DateRange(dt.date(2025, 4, 15), dt.date(2025, 5, 15))
    # April is in the heating season and May is not, so only 16 days count.
    assert profile.hours_in(window) == pytest.approx(16 * 24.0)


def test_hours_in_an_empty_window_are_none() -> None:
    profile = OperatingProfile.continuous()
    assert profile.hours_in(DateRange(dt.date(2025, 1, 1), dt.date(2025, 1, 1))) == 0.0


def test_the_load_factor_applies_to_a_window_too() -> None:
    profile = OperatingProfile("TRC", "Tracer", load_factor=0.5)
    january = DateRange(dt.date(2025, 1, 1), dt.date(2025, 2, 1))
    assert profile.hours_in(january) == pytest.approx(31 * 24.0 * 0.5)


def test_a_full_year_window_agrees_with_the_annual_figure() -> None:
    profile = OperatingProfile("HEAT", "Building heating", ServicePattern.HEATING_SEASON)
    year = DateRange.of_year(2025)
    assert profile.hours_in(year) == pytest.approx(profile.annual_hours(), rel=0.02)


def test_printing_a_profile() -> None:
    assert str(OperatingProfile.continuous()) == "CONT (8,760 h/y)"
