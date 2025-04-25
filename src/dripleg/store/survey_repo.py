"""Surveys, their readings, and the routes they were walked on.

A survey is saved whole. Writing one observation at a time as the tablet syncs
sounded reasonable and produced books where a survey was half imported and
nobody could tell, so the save takes the aggregate, replaces its readings inside
one transaction, and either the whole visit is there or the old one still is.
"""

from __future__ import annotations

import datetime as dt
import sqlite3

from dripleg.errors import NotFoundError
from dripleg.model.tags import SiteCode, TrapTag
from dripleg.store.codes import enum_from_value
from dripleg.store.db import Database
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

__all__ = ["RouteRepository", "SurveyRepository"]


def _site(site: SiteCode | str) -> SiteCode:
    return site if isinstance(site, SiteCode) else SiteCode.parse(site)


def _date(value: object) -> dt.date:
    return dt.date.fromisoformat(str(value))


class SurveyRepository:
    """Surveys and the observations on them."""

    def __init__(self, book: Database) -> None:
        self.book = book

    def save(self, survey: Survey) -> None:
        with self.book.transaction():
            self.book.execute(
                "INSERT INTO survey (site_code, reference, name, contractor, started_on, "
                "finished_on) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(site_code, reference) DO UPDATE SET name = excluded.name, "
                "contractor = excluded.contractor, started_on = excluded.started_on, "
                "finished_on = excluded.finished_on",
                (
                    survey.site.value,
                    survey.reference,
                    survey.name,
                    survey.contractor,
                    survey.started_on.isoformat(),
                    None if survey.finished_on is None else survey.finished_on.isoformat(),
                ),
            )
            self.book.execute(
                "DELETE FROM observation WHERE site_code = ? AND survey_reference = ?",
                (survey.site.value, survey.reference),
            )
            for observation in survey.observations:
                self._insert(survey.site, survey.reference, observation)

    def _insert(self, site: SiteCode, reference: str, observation: Observation) -> None:
        sound = observation.ultrasonic
        heat = observation.temperature
        self.book.execute(
            "INSERT INTO observation (site_code, survey_reference, tag, observed_on, "
            "technician, reported_condition, ultrasonic_db, ultrasonic_seconds, "
            "ultrasonic_cycles, ultrasonic_khz, upstream_f, downstream_f, ambient_f, "
            "temperature_method, sight_glass, measured_psia, note, photo_reference) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                site.value,
                reference,
                str(observation.tag),
                observation.observed_on.isoformat(),
                observation.technician,
                observation.reported_condition.value,
                None if sound is None else sound.decibels,
                None if sound is None else sound.seconds,
                None if sound is None else sound.cycles,
                None if sound is None else sound.frequency_khz,
                None if heat is None else heat.upstream.fahrenheit,
                None if heat is None else heat.downstream.fahrenheit,
                None if heat is None or heat.ambient is None else heat.ambient.fahrenheit,
                None if heat is None else heat.method.value,
                None if observation.sight_glass is None else observation.sight_glass.value,
                None
                if observation.measured_pressure is None
                else observation.measured_pressure.psia,
                observation.note,
                observation.photo_reference,
            ),
        )

    def get(self, site: SiteCode | str, reference: str) -> Survey:
        site_code = _site(site)
        wanted = reference.strip().upper()
        row = self.book.one(
            "SELECT * FROM survey WHERE site_code = ? AND reference = ?",
            (site_code.value, wanted),
        )
        if row is None:
            raise NotFoundError("survey", f"{site_code}/{wanted}")
        finished = row["finished_on"]
        survey = Survey(
            site=site_code,
            reference=str(row["reference"]),
            name=str(row["name"]),
            contractor=str(row["contractor"]),
            started_on=_date(row["started_on"]),
        )
        for line in self.book.query(
            "SELECT * FROM observation WHERE site_code = ? AND survey_reference = ? ORDER BY tag",
            (site_code.value, wanted),
        ):
            survey.record(self._observation_from(line))
        if finished is not None:
            survey.close(_date(finished))
        return survey

    def find(self, site: SiteCode | str, reference: str) -> Survey | None:
        try:
            return self.get(site, reference)
        except NotFoundError:
            return None

    def list_references(self, site: SiteCode | str) -> list[str]:
        rows = self.book.query(
            "SELECT reference FROM survey WHERE site_code = ? ORDER BY started_on, reference",
            (_site(site).value,),
        )
        return [str(row["reference"]) for row in rows]

    def readings_for(self, site: SiteCode | str, tag: TrapTag | str) -> list[Observation]:
        """Every reading ever taken on one trap, oldest first."""

        wanted = tag if isinstance(tag, TrapTag) else TrapTag.parse(tag)
        rows = self.book.query(
            "SELECT * FROM observation WHERE site_code = ? AND tag = ? ORDER BY observed_on",
            (_site(site).value, str(wanted)),
        )
        return [self._observation_from(row) for row in rows]

    @staticmethod
    def _observation_from(row: sqlite3.Row) -> Observation:
        sound = None
        if row["ultrasonic_db"] is not None:
            cycles = row["ultrasonic_cycles"]
            sound = UltrasonicReading(
                decibels=float(row["ultrasonic_db"]),
                seconds=float(row["ultrasonic_seconds"]),
                cycles=None if cycles is None else int(cycles),
                frequency_khz=float(row["ultrasonic_khz"] or 40.0),
            )
        heat = None
        if row["upstream_f"] is not None:
            ambient = row["ambient_f"]
            heat = TemperatureReading(
                upstream=Temperature.from_fahrenheit(float(row["upstream_f"])),
                downstream=Temperature.from_fahrenheit(float(row["downstream_f"])),
                ambient=None if ambient is None else Temperature.from_fahrenheit(float(ambient)),
                method=enum_from_value(
                    SurveyMethod, str(row["temperature_method"]), field="temperature_method"
                ),
            )
        glass = row["sight_glass"]
        pressure = row["measured_psia"]
        photo = row["photo_reference"]
        return Observation(
            tag=TrapTag.parse(str(row["tag"])),
            observed_on=_date(row["observed_on"]),
            technician=str(row["technician"]),
            reported_condition=enum_from_value(
                TrapCondition, str(row["reported_condition"]), field="reported_condition"
            ),
            ultrasonic=sound,
            temperature=heat,
            sight_glass=None
            if glass is None
            else enum_from_value(SightGlassView, str(glass), field="sight_glass"),
            measured_pressure=None if pressure is None else Pressure.from_psia(float(pressure)),
            note=str(row["note"]),
            photo_reference=None if photo is None else str(photo),
        )


class RouteRepository:
    """Routes and their stops, in walking order."""

    def __init__(self, book: Database) -> None:
        self.book = book

    def save(self, route: Route) -> None:
        with self.book.transaction():
            self.book.execute(
                "INSERT INTO route (site_code, code, name, minutes_per_stop, walk_minutes) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(site_code, code) DO UPDATE SET name = excluded.name, "
                "minutes_per_stop = excluded.minutes_per_stop, "
                "walk_minutes = excluded.walk_minutes",
                (
                    route.site.value,
                    route.code,
                    route.name,
                    route.minutes_per_stop,
                    route.walk_minutes,
                ),
            )
            self.book.execute(
                "DELETE FROM route_stop WHERE site_code = ? AND route_code = ?",
                (route.site.value, route.code),
            )
            self.book.execute_many(
                "INSERT INTO route_stop (site_code, route_code, position, tag) VALUES (?, ?, ?, ?)",
                [
                    (route.site.value, route.code, position, str(tag))
                    for position, tag in enumerate(route.stops)
                ],
            )

    def get(self, site: SiteCode | str, code: str) -> Route:
        site_code = _site(site)
        wanted = code.strip().upper()
        row = self.book.one(
            "SELECT * FROM route WHERE site_code = ? AND code = ?", (site_code.value, wanted)
        )
        if row is None:
            raise NotFoundError("route", f"{site_code}/{wanted}")
        stops = self.book.query(
            "SELECT tag FROM route_stop WHERE site_code = ? AND route_code = ? ORDER BY position",
            (site_code.value, wanted),
        )
        return Route(
            site=site_code,
            code=str(row["code"]),
            name=str(row["name"]),
            stops=[TrapTag.parse(str(stop["tag"])) for stop in stops],
            minutes_per_stop=float(row["minutes_per_stop"]),
            walk_minutes=float(row["walk_minutes"]),
        )

    def list_for(self, site: SiteCode | str) -> list[Route]:
        rows = self.book.query(
            "SELECT code FROM route WHERE site_code = ? ORDER BY code", (_site(site).value,)
        )
        return [self.get(site, str(row["code"])) for row in rows]

    def delete(self, site: SiteCode | str, code: str) -> bool:
        site_code = _site(site)
        wanted = code.strip().upper()
        before = self.book.scalar(
            "SELECT COUNT(*) FROM route WHERE site_code = ? AND code = ?",
            (site_code.value, wanted),
        )
        with self.book.transaction():
            self.book.execute(
                "DELETE FROM route WHERE site_code = ? AND code = ?", (site_code.value, wanted)
            )
        return bool(before)
