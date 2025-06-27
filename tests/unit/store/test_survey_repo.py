from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import pytest

from dripleg.errors import NotFoundError
from dripleg.model.plant import Site
from dripleg.model.tags import TrapTag
from dripleg.store.db import Database
from dripleg.store.migrations import migrate
from dripleg.store.plant_repo import PlantRepository
from dripleg.store.survey_repo import RouteRepository, SurveyRepository
from dripleg.survey.condition import TrapCondition
from dripleg.survey.observation import Observation
from dripleg.survey.readings import (
    SightGlassView,
    SurveyMethod,
    TemperatureReading,
    UltrasonicReading,
)
from dripleg.survey.route import Route
from dripleg.survey.survey import Survey
from dripleg.units.pressure import Pressure
from dripleg.units.temperature import Temperature

START = dt.date(2025, 4, 7)


@pytest.fixture
def book() -> Iterator[Database]:
    db = Database()
    migrate(db)
    PlantRepository(db).save_site(Site.of("WRX1", "Wrexham paper mill", "Bryn"))
    yield db
    db.close()


def a_survey() -> Survey:
    return Survey("WRX1", "S2025-1", "Spring machine room", "Vane Energy", START)


def full_reading(tag: str = "B12-MP-0043") -> Observation:
    return Observation(
        tag=TrapTag.parse(tag),
        observed_on=START + dt.timedelta(days=1),
        technician="R Ellis",
        reported_condition=TrapCondition.BLOWING_THROUGH,
        ultrasonic=UltrasonicReading(decibels=68.0, seconds=30.0, cycles=0, frequency_khz=38.0),
        temperature=TemperatureReading(
            upstream=Temperature.from_fahrenheit(345.0),
            downstream=Temperature.from_fahrenheit(338.0),
            ambient=Temperature.from_fahrenheit(74.0),
            method=SurveyMethod.INFRARED,
        ),
        sight_glass=SightGlassView.LIVE_STEAM,
        measured_pressure=Pressure.from_psig(118.0),
        note="plume off the vent",
        photo_reference="IMG_4411.jpg",
    )


def test_a_survey_round_trips_with_its_readings(book: Database) -> None:
    repo = SurveyRepository(book)
    survey = a_survey()
    survey.record(full_reading())
    survey.record(
        Observation(
            tag=TrapTag.parse("B12-MP-0044"),
            observed_on=START,
            technician="R Ellis",
            reported_condition=TrapCondition.OK,
        )
    )
    repo.save(survey)
    stored = repo.get("WRX1", "s2025-1")
    assert len(stored) == 2
    assert stored.name == "Spring machine room"
    assert stored.contractor == "Vane Energy"
    assert stored.started_on == START


def test_every_reading_field_survives(book: Database) -> None:
    repo = SurveyRepository(book)
    survey = a_survey()
    survey.record(full_reading())
    repo.save(survey)
    found = repo.get("WRX1", "S2025-1").find("B12-MP-43")
    assert found == full_reading()


def test_a_closed_survey_comes_back_closed(book: Database) -> None:
    repo = SurveyRepository(book)
    survey = a_survey()
    survey.record(full_reading())
    survey.close(START + dt.timedelta(days=3))
    repo.save(survey)
    stored = repo.get("WRX1", "S2025-1")
    assert stored.is_closed
    assert stored.finished_on == START + dt.timedelta(days=3)


def test_saving_a_survey_again_replaces_its_readings(book: Database) -> None:
    repo = SurveyRepository(book)
    survey = a_survey()
    survey.record(full_reading())
    repo.save(survey)
    survey.amend(full_reading().with_note("came back, it was fine"))
    repo.save(survey)
    stored = repo.get("WRX1", "S2025-1")
    assert len(stored) == 1
    found = stored.find("B12-MP-43")
    assert found is not None
    assert found.note == "came back, it was fine"


def test_a_reading_with_nothing_measured_round_trips(book: Database) -> None:
    repo = SurveyRepository(book)
    survey = a_survey()
    survey.record(
        Observation(
            tag=TrapTag.parse("B12-MP-1"),
            observed_on=START,
            technician="R Ellis",
            reported_condition=TrapCondition.NOT_FOUND,
        )
    )
    repo.save(survey)
    found = repo.get("WRX1", "S2025-1").find("B12-MP-1")
    assert found is not None
    assert found.ultrasonic is None
    assert found.temperature is None
    assert found.photo_reference is None
    assert found.measured_pressure is None


def test_a_missing_survey(book: Database) -> None:
    repo = SurveyRepository(book)
    with pytest.raises(NotFoundError, match="survey"):
        repo.get("WRX1", "NOPE")
    assert repo.find("WRX1", "NOPE") is None


def test_surveys_list_oldest_first(book: Database) -> None:
    repo = SurveyRepository(book)
    repo.save(Survey("WRX1", "S2025-2", "Autumn", "Vane", dt.date(2025, 10, 1)))
    repo.save(a_survey())
    assert repo.list_references("WRX1") == ["S2025-1", "S2025-2"]


def test_every_reading_on_one_trap_across_surveys(book: Database) -> None:
    repo = SurveyRepository(book)
    first = a_survey()
    first.record(full_reading())
    repo.save(first)
    second = Survey("WRX1", "S2025-2", "Autumn", "Vane", dt.date(2025, 10, 1))
    second.record(
        Observation(
            tag=TrapTag.parse("B12-MP-0043"),
            observed_on=dt.date(2025, 10, 2),
            technician="J Pike",
            reported_condition=TrapCondition.OK,
        )
    )
    repo.save(second)
    history = repo.readings_for("WRX1", "B12-MP-43")
    assert [o.observed_on for o in history] == [
        START + dt.timedelta(days=1),
        dt.date(2025, 10, 2),
    ]
    assert history[-1].technician == "J Pike"


def test_a_trap_with_no_history(book: Database) -> None:
    assert SurveyRepository(book).readings_for("WRX1", "B12-MP-1") == []


def test_a_route_round_trips_in_order(book: Database) -> None:
    repo = RouteRepository(book)
    route = Route.of("WRX1", "R1", "Ground floor", ["B12-MP-10", "B12-MP-2", "B12-LP-1"])
    route.minutes_per_stop = 8.0
    route.walk_minutes = 45.0
    repo.save(route)
    stored = repo.get("WRX1", "r1")
    assert [str(t) for t in stored.stops] == ["B12-MP-0010", "B12-MP-0002", "B12-LP-0001"]
    assert stored.minutes_per_stop == pytest.approx(8.0)
    assert stored.walk_minutes == pytest.approx(45.0)


def test_saving_a_route_again_replaces_its_stops(book: Database) -> None:
    repo = RouteRepository(book)
    repo.save(Route.of("WRX1", "R1", "Ground floor", ["B12-MP-1", "B12-MP-2"]))
    repo.save(Route.of("WRX1", "R1", "Ground floor", ["B12-MP-3"]))
    stored = repo.get("WRX1", "R1")
    assert [str(t) for t in stored.stops] == ["B12-MP-0003"]


def test_an_empty_route_round_trips(book: Database) -> None:
    repo = RouteRepository(book)
    repo.save(Route.of("WRX1", "R1", "Not walked yet"))
    assert len(repo.get("WRX1", "R1")) == 0


def test_routes_list_and_delete(book: Database) -> None:
    repo = RouteRepository(book)
    repo.save(Route.of("WRX1", "R2", "Second", ["B12-MP-1"]))
    repo.save(Route.of("WRX1", "R1", "First", ["B12-MP-2"]))
    assert [r.code for r in repo.list_for("WRX1")] == ["R1", "R2"]
    assert repo.delete("WRX1", "r1")
    assert [r.code for r in repo.list_for("WRX1")] == ["R2"]
    assert not repo.delete("WRX1", "R1")


def test_a_missing_route(book: Database) -> None:
    with pytest.raises(NotFoundError, match="route"):
        RouteRepository(book).get("WRX1", "R9")
