"""The trap model catalogue and the operating profiles, in and out of the book."""

from __future__ import annotations

import sqlite3

from dripleg.errors import NotFoundError
from dripleg.model.catalogue import TrapCatalogue, TrapModel
from dripleg.model.operating import OperatingProfile, ServicePattern
from dripleg.model.principles import OperatingPrinciple
from dripleg.model.tags import SiteCode
from dripleg.store.codes import enum_from_value, months_from_text, months_to_text
from dripleg.store.db import Database
from dripleg.store.keys import as_site
from dripleg.units.money import Money
from dripleg.units.pressure import Pressure

__all__ = ["CatalogueRepository", "ProfileRepository"]


class CatalogueRepository:
    """Trap models. Shared across sites, because the storeroom is."""

    def __init__(self, book: Database) -> None:
        self.book = book

    def save(self, model: TrapModel) -> None:
        with self.book.transaction():
            self.book.execute(
                "INSERT INTO trap_model (manufacturer, code, principle, orifice_diameter_in, "
                "max_operating_psia, max_back_pressure_pct, connection_size_in, "
                "connection_type, list_price_cents, discontinued, replaced_by, warranty_months) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(manufacturer, code) DO UPDATE SET "
                "principle = excluded.principle, "
                "orifice_diameter_in = excluded.orifice_diameter_in, "
                "max_operating_psia = excluded.max_operating_psia, "
                "max_back_pressure_pct = excluded.max_back_pressure_pct, "
                "connection_size_in = excluded.connection_size_in, "
                "connection_type = excluded.connection_type, "
                "list_price_cents = excluded.list_price_cents, "
                "discontinued = excluded.discontinued, "
                "replaced_by = excluded.replaced_by, "
                "warranty_months = excluded.warranty_months",
                (
                    model.manufacturer,
                    model.code,
                    model.principle.value,
                    model.orifice_diameter_in,
                    model.max_operating_pressure.psia,
                    model.max_back_pressure_percent,
                    model.connection_size_in,
                    model.connection_type,
                    model.list_price.cents,
                    1 if model.discontinued else 0,
                    model.replaced_by,
                    model.warranty_months,
                ),
            )

    def get(self, manufacturer: str, code: str) -> TrapModel:
        row = self.book.one(
            "SELECT * FROM trap_model WHERE manufacturer = ? AND code = ?",
            (manufacturer.strip().upper(), code.strip().upper()),
        )
        if row is None:
            raise NotFoundError("trap model", f"{manufacturer} {code}")
        return self._from(row)

    def find(self, manufacturer: str, code: str) -> TrapModel | None:
        try:
            return self.get(manufacturer, code)
        except NotFoundError:
            return None

    def load_catalogue(self) -> TrapCatalogue:
        rows = self.book.query("SELECT * FROM trap_model ORDER BY manufacturer, code")
        return TrapCatalogue([self._from(row) for row in rows])

    def save_catalogue(self, catalogue: TrapCatalogue) -> int:
        written = 0
        with self.book.transaction():
            for model in catalogue:
                self.save(model)
                written += 1
        return written

    @staticmethod
    def _from(row: sqlite3.Row) -> TrapModel:
        replaced = row["replaced_by"]
        return TrapModel(
            manufacturer=str(row["manufacturer"]),
            code=str(row["code"]),
            principle=enum_from_value(OperatingPrinciple, str(row["principle"]), field="principle"),
            orifice_diameter_in=float(row["orifice_diameter_in"]),
            max_operating_pressure=Pressure.from_psia(float(row["max_operating_psia"])),
            max_back_pressure_percent=float(row["max_back_pressure_pct"]),
            connection_size_in=float(row["connection_size_in"]),
            connection_type=str(row["connection_type"]),
            list_price=Money.from_cents(int(row["list_price_cents"])),
            discontinued=bool(row["discontinued"]),
            replaced_by=None if replaced is None else str(replaced),
            warranty_months=int(row["warranty_months"]),
        )


class ProfileRepository:
    """Operating profiles, which belong to a site because the seasons do."""

    def __init__(self, book: Database) -> None:
        self.book = book

    def save(self, site: SiteCode | str, profile: OperatingProfile) -> None:
        site_code = as_site(site)
        with self.book.transaction():
            self.book.execute(
                "INSERT INTO operating_profile (site_code, code, name, pattern, load_factor, "
                "campaign_months) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(site_code, code) DO UPDATE SET name = excluded.name, "
                "pattern = excluded.pattern, load_factor = excluded.load_factor, "
                "campaign_months = excluded.campaign_months",
                (
                    site_code.value,
                    profile.code,
                    profile.name,
                    profile.pattern.value,
                    profile.load_factor,
                    months_to_text(profile.campaign_months),
                ),
            )

    def get(self, site: SiteCode | str, code: str) -> OperatingProfile:
        site_code = as_site(site)
        row = self.book.one(
            "SELECT * FROM operating_profile WHERE site_code = ? AND code = ?",
            (site_code.value, code),
        )
        if row is None:
            raise NotFoundError("operating profile", f"{site_code}/{code}")
        return self._from(row)

    def list_for(self, site: SiteCode | str) -> list[OperatingProfile]:
        site_code = as_site(site)
        rows = self.book.query(
            "SELECT * FROM operating_profile WHERE site_code = ? ORDER BY code",
            (site_code.value,),
        )
        return [self._from(row) for row in rows]

    @staticmethod
    def _from(row: sqlite3.Row) -> OperatingProfile:
        return OperatingProfile(
            code=str(row["code"]),
            name=str(row["name"]),
            pattern=enum_from_value(ServicePattern, str(row["pattern"]), field="pattern"),
            load_factor=float(row["load_factor"]),
            campaign_months=months_from_text(str(row["campaign_months"])),
        )
