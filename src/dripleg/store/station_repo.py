"""Trap stations, and hydrating a whole register out of one query.

A station row points at four other rows: its header, its model, its profile and
its area. Fetching those one at a time per station is the difference between a
register that loads in a blink and one that takes a minute on a plant with four
thousand traps, so the register load reads the lot in five queries and joins
them in Python.
"""

from __future__ import annotations

import sqlite3

from dripleg.errors import NotFoundError
from dripleg.model.attributes import Accessibility, Criticality, ServiceType
from dripleg.model.catalogue import TrapModel
from dripleg.model.header import DischargeDestination, SteamHeader
from dripleg.model.installation import TrapInstallation
from dripleg.model.operating import OperatingProfile
from dripleg.model.register import TrapRegister
from dripleg.model.tags import SiteCode, TrapTag
from dripleg.store.catalogue_repo import CatalogueRepository, ProfileRepository
from dripleg.store.codes import enum_from_value
from dripleg.store.db import Database
from dripleg.store.keys import as_date, as_site, as_tag
from dripleg.store.plant_repo import PlantRepository

__all__ = ["StationRepository"]

_COLUMNS = (
    "site_code, tag, area_code, system_code, sequence, model_manufacturer, model_code, "
    "service, accessibility, criticality, profile_code, installed_on, removed_on, "
    "destination, strainer_fitted, isolation_valves, test_valve_fitted, insulated, "
    "interval_months_override, pipe_nominal, run_length_ft, warmup_minutes, note"
)


_UPSERT = (
    f"INSERT INTO trap_station ({_COLUMNS}) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT(site_code, tag) DO UPDATE SET "
    "area_code = excluded.area_code, system_code = excluded.system_code, "
    "sequence = excluded.sequence, "
    "model_manufacturer = excluded.model_manufacturer, "
    "model_code = excluded.model_code, service = excluded.service, "
    "accessibility = excluded.accessibility, criticality = excluded.criticality, "
    "profile_code = excluded.profile_code, installed_on = excluded.installed_on, "
    "removed_on = excluded.removed_on, destination = excluded.destination, "
    "strainer_fitted = excluded.strainer_fitted, "
    "isolation_valves = excluded.isolation_valves, "
    "test_valve_fitted = excluded.test_valve_fitted, "
    "insulated = excluded.insulated, "
    "interval_months_override = excluded.interval_months_override, "
    "pipe_nominal = excluded.pipe_nominal, "
    "run_length_ft = excluded.run_length_ft, "
    "warmup_minutes = excluded.warmup_minutes, "
    "note = excluded.note"
)


class StationRepository:
    """Trap stations, one site at a time."""

    def __init__(self, book: Database) -> None:
        self.book = book
        self.plant = PlantRepository(book)
        self.catalogue = CatalogueRepository(book)
        self.profiles = ProfileRepository(book)

    def save(self, station: TrapInstallation) -> None:
        with self.book.transaction():
            self.book.execute(_UPSERT, self._values(station))

    @staticmethod
    def _values(station: TrapInstallation) -> tuple[object, ...]:
        return (
            station.site.value,
            str(station.tag),
            station.tag.area.value,
            station.tag.system.value,
            station.tag.sequence,
            station.model.manufacturer,
            station.model.code,
            station.service.value,
            station.accessibility.value,
            station.criticality.value,
            station.profile.code,
            station.installed_on.isoformat(),
            None if station.removed_on is None else station.removed_on.isoformat(),
            None if station.destination is None else station.destination.value,
            1 if station.strainer_fitted else 0,
            station.isolation_valves,
            1 if station.test_valve_fitted else 0,
            1 if station.insulated else 0,
            station.interval_months_override,
            station.pipe_nominal,
            station.run_length_ft,
            station.warmup_minutes,
            station.note,
        )

    def get(self, site: SiteCode | str, tag: TrapTag | str) -> TrapInstallation:
        site_code = as_site(site)
        wanted = as_tag(tag)
        row = self.book.one(
            "SELECT * FROM trap_station WHERE site_code = ? AND tag = ?",
            (site_code.value, str(wanted)),
        )
        if row is None:
            raise NotFoundError("trap station", f"{site_code}/{wanted}")
        header = self.plant.get_header(site_code, str(row["area_code"]), str(row["system_code"]))
        model = self.catalogue.get(str(row["model_manufacturer"]), str(row["model_code"]))
        profile = self.profiles.get(site_code, str(row["profile_code"]))
        return self._from(row, header, model, profile)

    def find(self, site: SiteCode | str, tag: TrapTag | str) -> TrapInstallation | None:
        try:
            return self.get(site, tag)
        except NotFoundError:
            return None

    def delete(self, site: SiteCode | str, tag: TrapTag | str) -> bool:
        site_code = as_site(site)
        wanted = as_tag(tag)
        before = self.book.scalar(
            "SELECT COUNT(*) FROM trap_station WHERE site_code = ? AND tag = ?",
            (site_code.value, str(wanted)),
        )
        with self.book.transaction():
            self.book.execute(
                "DELETE FROM trap_station WHERE site_code = ? AND tag = ?",
                (site_code.value, str(wanted)),
            )
        return bool(before)

    def load_register(self, site: SiteCode | str) -> TrapRegister:
        """Every station at a site, with its header, model and profile attached."""

        site_code = as_site(site)
        headers = {h.key: h for h in self.plant.list_headers(site_code)}
        catalogue = self.catalogue.load_catalogue()
        profiles = {p.code: p for p in self.profiles.list_for(site_code)}
        rows = self.book.query(
            "SELECT * FROM trap_station WHERE site_code = ? "
            "ORDER BY area_code, system_code, sequence",
            (site_code.value,),
        )
        register = TrapRegister()
        for row in rows:
            key = (site_code.value, str(row["area_code"]), str(row["system_code"]))
            header = headers.get(key)
            if header is None:
                raise NotFoundError("header", "/".join(key))
            model = catalogue.find(str(row["model_manufacturer"]), str(row["model_code"]))
            if model is None:
                raise NotFoundError(
                    "trap model", f"{row['model_manufacturer']} {row['model_code']}"
                )
            profile = profiles.get(str(row["profile_code"]))
            if profile is None:
                raise NotFoundError("operating profile", str(row["profile_code"]))
            register.add(self._from(row, header, model, profile))
        return register

    def save_register(self, register: TrapRegister) -> int:
        return self.save_many(list(register))

    def save_many(self, stations: list[TrapInstallation]) -> int:
        """Write a batch of stations through one statement.

        A register import on a plant with four thousand traps was four thousand
        round trips, one per station, and the whole of that time was the round
        trip rather than the write. `executemany` on the same upsert takes it to
        one, and the transaction was already there.
        """

        if not stations:
            return 0
        with self.book.transaction():
            self.book.execute_many(_UPSERT, [self._values(station) for station in stations])
        return len(stations)

    def count(self, site: SiteCode | str) -> int:
        site_code = as_site(site)
        return int(
            self.book.scalar(
                "SELECT COUNT(*) FROM trap_station WHERE site_code = ?", (site_code.value,)
            )
            or 0
        )

    @staticmethod
    def _from(
        row: sqlite3.Row,
        header: SteamHeader,
        model: TrapModel,
        profile: OperatingProfile,
    ) -> TrapInstallation:
        removed = row["removed_on"]
        destination = row["destination"]
        override = row["interval_months_override"]
        return TrapInstallation(
            site=SiteCode(str(row["site_code"])),
            tag=TrapTag.parse(str(row["tag"])),
            header=header,
            model=model,
            service=enum_from_value(ServiceType, str(row["service"]), field="service"),
            accessibility=enum_from_value(
                Accessibility, str(row["accessibility"]), field="accessibility"
            ),
            criticality=enum_from_value(Criticality, str(row["criticality"]), field="criticality"),
            profile=profile,
            installed_on=as_date(row["installed_on"]),
            destination=None
            if destination is None
            else enum_from_value(DischargeDestination, str(destination), field="destination"),
            removed_on=None if removed is None else as_date(removed),
            strainer_fitted=bool(row["strainer_fitted"]),
            isolation_valves=int(row["isolation_valves"]),
            test_valve_fitted=bool(row["test_valve_fitted"]),
            insulated=bool(row["insulated"]),
            interval_months_override=None if override is None else int(override),
            pipe_nominal=None if row["pipe_nominal"] is None else str(row["pipe_nominal"]),
            run_length_ft=(None if row["run_length_ft"] is None else float(row["run_length_ft"])),
            warmup_minutes=float(row["warmup_minutes"] or 30.0),
            note=str(row["note"]),
        )
