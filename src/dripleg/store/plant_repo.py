"""Reading and writing sites, areas and headers.

Repositories here are plain classes over a `Database`, one per area of the
model, and they hand back model objects rather than rows. Nothing above this
layer sees sqlite and nothing below it sees a `Pressure`.

Writes are upserts on the natural key. A survey contractor re-imports the same
asset register three times in a week and the second import must not be an
error, it must be the same register.
"""

from __future__ import annotations

import sqlite3

from dripleg.errors import NotFoundError
from dripleg.model.header import DischargeDestination, SteamHeader
from dripleg.model.plant import Area, Site
from dripleg.model.tags import AreaCode, SiteCode, SystemCode
from dripleg.store.codes import enum_from_value
from dripleg.store.db import Database
from dripleg.store.keys import as_area, as_site, as_system
from dripleg.units.pressure import Pressure

__all__ = ["PlantRepository"]


class PlantRepository:
    """Sites, areas and headers, in and out of the book."""

    def __init__(self, book: Database) -> None:
        self.book = book

    # Sites ----------------------------------------------------------------

    def save_site(self, site: Site) -> None:
        with self.book.transaction():
            self.book.execute(
                "INSERT INTO site (code, name, operator, programme_start_month, "
                "fuel_price_basis) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(code) DO UPDATE SET name = excluded.name, "
                "operator = excluded.operator, "
                "programme_start_month = excluded.programme_start_month, "
                "fuel_price_basis = excluded.fuel_price_basis",
                (
                    site.code.value,
                    site.name,
                    site.operator,
                    site.programme_start_month,
                    site.fuel_price_basis,
                ),
            )

    def get_site(self, code: SiteCode | str) -> Site:
        wanted = code if isinstance(code, SiteCode) else SiteCode.parse(code)
        row = self.book.one("SELECT * FROM site WHERE code = ?", (wanted.value,))
        if row is None:
            raise NotFoundError("site", wanted.value)
        return self._site_from(row)

    def find_site(self, code: SiteCode | str) -> Site | None:
        try:
            return self.get_site(code)
        except NotFoundError:
            return None

    def list_sites(self) -> list[Site]:
        return [self._site_from(row) for row in self.book.query("SELECT * FROM site ORDER BY code")]

    @staticmethod
    def _site_from(row: sqlite3.Row) -> Site:
        return Site(
            code=SiteCode(str(row["code"])),
            name=str(row["name"]),
            operator=str(row["operator"]),
            programme_start_month=int(row["programme_start_month"]),
            fuel_price_basis=str(row["fuel_price_basis"]),
        )

    # Areas ----------------------------------------------------------------

    def save_area(self, area: Area) -> None:
        with self.book.transaction():
            self.book.execute(
                "INSERT INTO area (site_code, code, name, cost_centre, parent_code) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(site_code, code) DO UPDATE SET name = excluded.name, "
                "cost_centre = excluded.cost_centre, parent_code = excluded.parent_code",
                (
                    area.site.value,
                    area.code.value,
                    area.name,
                    area.cost_centre,
                    None if area.parent is None else area.parent.value,
                ),
            )

    def get_area(self, site: SiteCode | str, code: AreaCode | str) -> Area:
        site_code = as_site(site)
        area_code = as_area(code)
        row = self.book.one(
            "SELECT * FROM area WHERE site_code = ? AND code = ?",
            (site_code.value, area_code.value),
        )
        if row is None:
            raise NotFoundError("area", f"{site_code}/{area_code}")
        return self._area_from(row)

    def list_areas(self, site: SiteCode | str) -> list[Area]:
        site_code = as_site(site)
        rows = self.book.query(
            "SELECT * FROM area WHERE site_code = ? ORDER BY code", (site_code.value,)
        )
        return [self._area_from(row) for row in rows]

    def children_of(self, site: SiteCode | str, parent: AreaCode | str) -> list[Area]:
        site_code = as_site(site)
        parent_code = parent if isinstance(parent, AreaCode) else AreaCode.parse(parent)
        rows = self.book.query(
            "SELECT * FROM area WHERE site_code = ? AND parent_code = ? ORDER BY code",
            (site_code.value, parent_code.value),
        )
        return [self._area_from(row) for row in rows]

    @staticmethod
    def _area_from(row: sqlite3.Row) -> Area:
        parent = row["parent_code"]
        return Area(
            site=SiteCode(str(row["site_code"])),
            code=AreaCode(str(row["code"])),
            name=str(row["name"]),
            cost_centre=str(row["cost_centre"]),
            parent=None if parent is None else AreaCode(str(parent)),
        )

    # Headers --------------------------------------------------------------

    def save_header(self, header: SteamHeader) -> None:
        with self.book.transaction():
            self.book.execute(
                "INSERT INTO header (site_code, area_code, system_code, name, operating_psia, "
                "design_psia, discharge_psia, destination) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(site_code, area_code, system_code) DO UPDATE SET "
                "name = excluded.name, operating_psia = excluded.operating_psia, "
                "design_psia = excluded.design_psia, "
                "discharge_psia = excluded.discharge_psia, "
                "destination = excluded.destination",
                (
                    header.site.value,
                    header.area.value,
                    header.system.value,
                    header.name,
                    header.operating_pressure.psia,
                    header.design_pressure.psia,
                    header.discharge_pressure.psia,
                    header.destination.value,
                ),
            )

    def get_header(
        self,
        site: SiteCode | str,
        area: AreaCode | str,
        system: SystemCode | str,
    ) -> SteamHeader:
        key = self._header_key(site, area, system)
        row = self.book.one(
            "SELECT * FROM header WHERE site_code = ? AND area_code = ? AND system_code = ?",
            key,
        )
        if row is None:
            raise NotFoundError("header", "/".join(key))
        return self._header_from(row)

    def list_headers(
        self, site: SiteCode | str, area: AreaCode | str | None = None
    ) -> list[SteamHeader]:
        site_code = as_site(site)
        if area is None:
            rows = self.book.query(
                "SELECT * FROM header WHERE site_code = ? ORDER BY area_code, system_code",
                (site_code.value,),
            )
        else:
            area_code = as_area(area)
            rows = self.book.query(
                "SELECT * FROM header WHERE site_code = ? AND area_code = ? ORDER BY system_code",
                (site_code.value, area_code.value),
            )
        return [self._header_from(row) for row in rows]

    @staticmethod
    def _header_key(
        site: SiteCode | str,
        area: AreaCode | str,
        system: SystemCode | str,
    ) -> tuple[str, str, str]:
        site_code = as_site(site)
        area_code = as_area(area)
        system_code = as_system(system)
        return (site_code.value, area_code.value, system_code.value)

    @staticmethod
    def _header_from(row: sqlite3.Row) -> SteamHeader:
        return SteamHeader(
            site=SiteCode(str(row["site_code"])),
            area=AreaCode(str(row["area_code"])),
            system=SystemCode(str(row["system_code"])),
            name=str(row["name"]),
            operating_pressure=Pressure.from_psia(float(row["operating_psia"])),
            design_pressure=Pressure.from_psia(float(row["design_psia"])),
            discharge_pressure=Pressure.from_psia(float(row["discharge_psia"])),
            destination=enum_from_value(
                DischargeDestination, str(row["destination"]), field="destination"
            ),
        )
