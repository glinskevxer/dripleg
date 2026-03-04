"""The boiler house numbers, kept per site rather than passed in every time.

Fuel price, feedwater temperature, boiler efficiency and the rest are site
facts that change once or twice a year, and a report that takes them as command
line arguments produces a different answer every time somebody forgets one. So
they live in the book, dated, and every costing reads them from there.

Prices are stored as text rather than as floats, so `6.2537` comes back as
`6.2537` and not as something that rounds to it.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from dripleg.errors import NotFoundError
from dripleg.loss.cost import CostBasis
from dripleg.loss.emissions import EmissionsFactor, factor_named
from dripleg.loss.energy import EnergyModel
from dripleg.model.tags import SiteCode
from dripleg.repair.recommend import RepairBasis
from dripleg.store.db import Database
from dripleg.store.keys import as_site
from dripleg.units.money import Money, Price
from dripleg.units.temperature import Temperature

__all__ = ["BasisRepository", "SiteBasis"]


@dataclass(frozen=True)
class SiteBasis:
    """Everything a costing needs, in one object."""

    costs: CostBasis
    energy: EnergyModel
    repairs: RepairBasis
    factor: EmissionsFactor
    effective_from: dt.date

    @classmethod
    def typical(cls, effective_from: dt.date | None = None) -> SiteBasis:
        return cls(
            costs=CostBasis.typical(),
            energy=EnergyModel.typical(),
            repairs=RepairBasis.typical(),
            factor=factor_named("natural gas"),
            effective_from=effective_from or dt.date(2025, 1, 1),
        )

    def facts(self) -> dict[str, object]:
        return {
            "fuel": str(self.costs.fuel),
            "water": str(self.costs.water),
            "effluent": str(self.costs.effluent),
            "chemical": str(self.costs.chemical),
            "labour": str(self.repairs.labour),
            "permit": str(self.repairs.permit_cost),
            "feedwater_f": round(self.energy.feedwater_temperature.fahrenheit, 1),
            "boiler_efficiency": self.energy.boiler_efficiency,
            "condensate_returned": self.energy.condensate_returned,
            "receiver_vent_fraction": self.energy.receiver_vent_fraction,
            "emissions_factor": self.factor.name,
            "kg_co2e_per_mmbtu": self.factor.kg_co2e_per_mmbtu,
            "effective_from": self.effective_from.isoformat(),
        }


class BasisRepository:
    """One row per site, replaced whenever the numbers move."""

    def __init__(self, book: Database) -> None:
        self.book = book

    def save(self, site: SiteCode | str, basis: SiteBasis) -> None:
        site_code = as_site(site)
        with self.book.transaction():
            self.book.execute(
                "INSERT INTO cost_basis (site_code, fuel_per_mmbtu, water_per_kgal, "
                "effluent_per_kgal, chemical_per_kgal, labour_per_hour, permit_cost_cents, "
                "feedwater_f, boiler_efficiency, condensate_returned, "
                "receiver_vent_fraction, fuel, effective_from) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(site_code) DO UPDATE SET "
                "fuel_per_mmbtu = excluded.fuel_per_mmbtu, "
                "water_per_kgal = excluded.water_per_kgal, "
                "effluent_per_kgal = excluded.effluent_per_kgal, "
                "chemical_per_kgal = excluded.chemical_per_kgal, "
                "labour_per_hour = excluded.labour_per_hour, "
                "permit_cost_cents = excluded.permit_cost_cents, "
                "feedwater_f = excluded.feedwater_f, "
                "boiler_efficiency = excluded.boiler_efficiency, "
                "condensate_returned = excluded.condensate_returned, "
                "receiver_vent_fraction = excluded.receiver_vent_fraction, "
                "fuel = excluded.fuel, effective_from = excluded.effective_from",
                (
                    site_code.value,
                    str(basis.costs.fuel.dollars_per_unit),
                    str(basis.costs.water.dollars_per_unit),
                    str(basis.costs.effluent.dollars_per_unit),
                    str(basis.costs.chemical.dollars_per_unit),
                    str(basis.repairs.labour.dollars_per_unit),
                    basis.repairs.permit_cost.cents,
                    basis.energy.feedwater_temperature.fahrenheit,
                    basis.energy.boiler_efficiency,
                    basis.energy.condensate_returned,
                    basis.energy.receiver_vent_fraction,
                    basis.factor.name,
                    basis.effective_from.isoformat(),
                ),
            )

    def get(self, site: SiteCode | str) -> SiteBasis:
        site_code = as_site(site)
        row = self.book.one("SELECT * FROM cost_basis WHERE site_code = ?", (site_code.value,))
        if row is None:
            raise NotFoundError("cost basis", site_code.value)
        return self._from(row)

    def get_or_default(self, site: SiteCode | str) -> SiteBasis:
        """The site's numbers, or the worked example if it has none yet."""

        try:
            return self.get(site)
        except NotFoundError:
            return SiteBasis.typical()

    @staticmethod
    def _from(row: sqlite3.Row) -> SiteBasis:
        return SiteBasis(
            costs=CostBasis(
                fuel=Price(Decimal(str(row["fuel_per_mmbtu"])), "MMBtu"),
                water=Price(Decimal(str(row["water_per_kgal"])), "1000 gal"),
                effluent=Price(Decimal(str(row["effluent_per_kgal"])), "1000 gal"),
                chemical=Price(Decimal(str(row["chemical_per_kgal"])), "1000 gal"),
            ),
            energy=EnergyModel(
                feedwater_temperature=Temperature.from_fahrenheit(float(row["feedwater_f"])),
                boiler_efficiency=float(row["boiler_efficiency"]),
                condensate_returned=float(row["condensate_returned"]),
                receiver_vent_fraction=float(row["receiver_vent_fraction"]),
            ),
            repairs=RepairBasis(
                labour=Price(Decimal(str(row["labour_per_hour"])), "h"),
                permit_cost=Money.from_cents(int(row["permit_cost_cents"])),
            ),
            factor=factor_named(str(row["fuel"])),
            effective_from=dt.date.fromisoformat(str(row["effective_from"])),
        )
