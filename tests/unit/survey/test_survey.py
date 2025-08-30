from __future__ import annotations

import datetime as dt

import pytest

from dripleg.errors import ConflictError, ValidationError
from dripleg.model.attributes import Accessibility, Criticality, ServiceType
from dripleg.model.catalogue import ConnectionType, TrapModel
from dripleg.model.header import SteamHeader
from dripleg.model.installation import TrapInstallation
from dripleg.model.operating import OperatingProfile
from dripleg.model.plant import Area
from dripleg.model.principles import OperatingPrinciple
from dripleg.model.register import TrapRegister
from dripleg.model.tags import SiteCode, TrapTag
from dripleg.survey.condition import TrapCondition
from dripleg.survey.observation import Observation
from dripleg.survey.survey import Survey
from dripleg.units.money import Money
from dripleg.units.pressure import Pressure

START = dt.date(2025, 4, 7)
MODEL = TrapModel(
    manufacturer="Halden",
    code="TD52",
    principle=OperatingPrinciple.THERMODYNAMIC_DISC,
    orifice_diameter_in=0.093,
    max_operating_pressure=Pressure.from_psig(600.0),
    max_back_pressure_percent=80.0,
    connection_size_in=0.5,
    connection_type=ConnectionType.SCREWED,
    list_price=Money.from_dollars("184.00"),
)


def a_register(tags: list[str]) -> TrapRegister:
    stations = []
    for text in tags:
        tag = TrapTag.parse(text)
        area = Area.of("WRX1", tag.area.value, "Area", "CC1")
        stations.append(
            TrapInstallation(
                site=SiteCode("WRX1"),
                tag=tag,
                header=SteamHeader.of(area, tag.system.value, "Main", 125.0),
                model=MODEL,
                service=ServiceType.DRIP,
                accessibility=Accessibility.GROUND_LEVEL,
                criticality=Criticality.NUISANCE,
                profile=OperatingProfile.continuous(),
                installed_on=dt.date(2021, 6, 14),
            )
        )
    return TrapRegister(stations)


def a_survey() -> Survey:
    return Survey("WRX1", "s2025-1", "Spring machine room", "Vane Energy", START)


def reading(tag: str, condition: TrapCondition, day: dt.date = START) -> Observation:
    return Observation(
        tag=TrapTag.parse(tag),
        observed_on=day,
        technician="R Ellis",
        reported_condition=condition,
    )


def test_a_survey_normalises_its_reference_and_names() -> None:
    survey = a_survey()
    assert survey.reference == "S2025-1"
    assert survey.name == "Spring machine room"
    assert survey.contractor == "Vane Energy"
    assert not survey.is_closed


def test_a_survey_needs_its_three_names() -> None:
    with pytest.raises(ValidationError, match="needs a reference"):
        Survey("WRX1", "  ", "Name", "Contractor", START)
    with pytest.raises(ValidationError, match="needs a name"):
        Survey("WRX1", "S1", " ", "Contractor", START)
    with pytest.raises(ValidationError, match="needs a contractor"):
        Survey("WRX1", "S1", "Name", "", START)


def test_a_survey_cannot_end_before_it_starts() -> None:
    with pytest.raises(ValidationError, match="end before it starts"):
        Survey("WRX1", "S1", "Name", "C", START, finished_on=START - dt.timedelta(days=1))


def test_readings_go_in_and_come_back_in_tag_order() -> None:
    survey = a_survey()
    survey.record(reading("B12-MP-2", TrapCondition.OK))
    survey.record(reading("B12-MP-1", TrapCondition.LEAKING))
    assert [str(o.tag) for o in survey.observations] == ["B12-MP-0001", "B12-MP-0002"]
    assert len(survey) == 2
    assert "b12-mp-1" in survey
    assert survey.find("B12-MP-1") is not None


def test_a_trap_can_only_be_read_once_on_a_survey() -> None:
    survey = a_survey()
    survey.record(reading("B12-MP-1", TrapCondition.OK))
    with pytest.raises(ConflictError, match="already been read"):
        survey.record(reading("B12-MP-1", TrapCondition.LEAKING))


def test_a_reading_before_the_survey_started_is_refused() -> None:
    survey = a_survey()
    with pytest.raises(ValidationError, match="before the survey started"):
        survey.record(reading("B12-MP-1", TrapCondition.OK, START - dt.timedelta(days=2)))


def test_a_return_visit_amends_the_reading() -> None:
    survey = a_survey()
    survey.record(reading("B12-MP-1", TrapCondition.INACCESSIBLE))
    survey.amend(reading("B12-MP-1", TrapCondition.BLOWING_THROUGH))
    found = survey.find("B12-MP-1")
    assert found is not None
    assert found.reported_condition is TrapCondition.BLOWING_THROUGH
    assert len(survey) == 1


def test_a_closed_survey_takes_no_amendments_either() -> None:
    survey = a_survey()
    survey.record(reading("B12-MP-1", TrapCondition.OK))
    survey.close(START + dt.timedelta(days=2))
    with pytest.raises(ConflictError, match="is closed"):
        survey.amend(reading("B12-MP-1", TrapCondition.LEAKING))


def test_amending_something_that_was_never_read() -> None:
    with pytest.raises(ConflictError, match="has not been read"):
        a_survey().amend(reading("B12-MP-1", TrapCondition.OK))


def test_closing_a_survey_stops_it_taking_readings() -> None:
    survey = a_survey()
    survey.record(reading("B12-MP-1", TrapCondition.OK, START + dt.timedelta(days=1)))
    survey.close(START + dt.timedelta(days=2))
    assert survey.is_closed
    with pytest.raises(ConflictError, match="is closed"):
        survey.record(reading("B12-MP-2", TrapCondition.OK))
    with pytest.raises(ConflictError, match="already closed"):
        survey.close(START + dt.timedelta(days=3))


def test_a_survey_cannot_close_before_its_last_reading() -> None:
    survey = a_survey()
    survey.record(reading("B12-MP-1", TrapCondition.OK, START + dt.timedelta(days=3)))
    with pytest.raises(ValidationError, match="before its last reading"):
        survey.close(START + dt.timedelta(days=1))


def test_an_empty_survey_cannot_close_before_it_starts() -> None:
    with pytest.raises(ValidationError, match="before it starts"):
        a_survey().close(START - dt.timedelta(days=1))


def test_the_window_runs_to_the_last_reading_while_open() -> None:
    survey = a_survey()
    assert survey.window.days == 1
    survey.record(reading("B12-MP-1", TrapCondition.OK, START + dt.timedelta(days=2)))
    assert survey.window.days == 3
    survey.close(START + dt.timedelta(days=4))
    assert survey.window.days == 5


def test_condition_counts_come_back_worst_first() -> None:
    survey = a_survey()
    survey.record(reading("B12-MP-1", TrapCondition.OK))
    survey.record(reading("B12-MP-2", TrapCondition.BLOWING_THROUGH))
    survey.record(reading("B12-MP-3", TrapCondition.OK))
    counts = survey.condition_counts()
    assert list(counts) == [TrapCondition.BLOWING_THROUGH, TrapCondition.OK]
    assert counts[TrapCondition.OK] == 2


def test_the_two_failure_rates_have_different_denominators() -> None:
    survey = a_survey()
    survey.record(reading("B12-MP-1", TrapCondition.BLOWING_THROUGH))
    survey.record(reading("B12-MP-2", TrapCondition.OK))
    survey.record(reading("B12-MP-3", TrapCondition.NOT_FOUND))
    assert len(survey.failures()) == 1
    assert len(survey.assessed()) == 2
    assert survey.failure_rate() == pytest.approx(0.5)
    assert survey.failure_rate(over_assessed=False) == pytest.approx(1 / 3)


def test_a_survey_with_nothing_on_it_has_no_failure_rate() -> None:
    assert a_survey().failure_rate() == 0.0
    assert a_survey().failure_rate(over_assessed=False) == 0.0


def test_coverage_counts_the_register_not_the_readings() -> None:
    register = a_register(["B12-MP-1", "B12-MP-2", "B12-MP-3", "B12-MP-4"])
    survey = a_survey()
    survey.record(reading("B12-MP-1", TrapCondition.OK))
    survey.record(reading("B12-MP-2", TrapCondition.NOT_FOUND))
    survey.record(reading("B12-MP-3", TrapCondition.INACCESSIBLE))
    coverage = survey.coverage(register)
    assert coverage.on_register == 4
    assert coverage.observed == 3
    assert coverage.assessed == 1
    assert coverage.not_found == 1
    assert coverage.inaccessible == 1
    assert coverage.not_visited == 1
    assert coverage.assessed_fraction == pytest.approx(0.25)
    assert coverage.visited_fraction == pytest.approx(0.75)
    assert not coverage.is_complete


def test_full_coverage_says_so() -> None:
    register = a_register(["B12-MP-1"])
    survey = a_survey()
    survey.record(reading("B12-MP-1", TrapCondition.OK))
    assert survey.coverage(register).is_complete


def test_coverage_of_an_empty_register() -> None:
    coverage = a_survey().coverage(a_register([]))
    assert coverage.assessed_fraction == 0.0
    assert coverage.visited_fraction == 0.0
    assert not coverage.is_complete


def test_a_trap_found_that_nobody_had_written_down() -> None:
    register = a_register(["B12-MP-1"])
    survey = a_survey()
    survey.record(reading("B12-MP-1", TrapCondition.OK))
    survey.record(reading("B12-MP-9", TrapCondition.LEAKING))
    assert [str(t) for t in survey.observed_but_not_on_register(register)] == ["B12-MP-0009"]
    assert survey.coverage(register).observed == 1


def test_printing_coverage_and_a_survey() -> None:
    register = a_register(["B12-MP-1", "B12-MP-2"])
    survey = a_survey()
    survey.record(reading("B12-MP-1", TrapCondition.OK))
    assert str(survey.coverage(register)) == "1 of 2 assessed (50.0%), 1 not visited"
    assert str(survey) == "S2025-1 Spring machine room (1 readings, open)"
