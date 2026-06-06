"""The energy and carbon view of a survey, which goes to a different reader.

The money report answers what it costs. This answers what it burns, and the two
do not rank the same: a trap on a heating main that only runs half the year
loses fewer MMBtu per pound of steam than one on a process main at the same
pressure, and a plant chasing a carbon number rather than a fuel bill will pick
a different ten traps to fix first.

Both figures are on the row so nobody has to hold two reports side by side.
"""

from __future__ import annotations

from dataclasses import dataclass

from dripleg.loss.register import LossRegister
from dripleg.report.base import Rendered
from dripleg.report.table import Column, Table
from dripleg.units.energy import Energy
from dripleg.units.flow import Mass

__all__ = ["EnergyReport", "build_energy_report"]


@dataclass(frozen=True)
class EnergyReport(Rendered):
    """A survey's steam, fuel and carbon, by trap and by area."""

    reference: str
    factor: str
    kg_per_mmbtu: float
    steam: Mass
    fuel: Energy
    tonnes_co2e: float
    makeup_pounds: float
    rows: list[tuple[str, str, str, str, str]]
    by_area: list[tuple[str, str, str]]

    @property
    def headline(self) -> str:
        return (
            f"{self.reference}: {self.fuel.mmbtu:,.0f} MMBtu of fuel and "
            f"{self.tonnes_co2e:,.1f} t CO2e a year on the {self.factor} factor"
        )

    def summary_lines(self) -> list[str]:
        return [
            f"steam lost      {self.steam.pounds:,.0f} lb a year",
            f"makeup water    {self.makeup_pounds:,.0f} lb a year",
            f"fuel            {self.fuel.mmbtu:,.1f} MMBtu a year",
            f"carbon          {self.tonnes_co2e:,.2f} t CO2e a year",
            f"factor          {self.factor} at {self.kg_per_mmbtu:.1f} kg/MMBtu",
        ]

    def trap_table(self) -> Table:
        table = Table(
            [
                Column("tag"),
                Column("condition"),
                Column.number("lb/y"),
                Column.number("MMBtu/y"),
                Column.number("t CO2e/y"),
            ]
        )
        table.extend(self.rows)
        return table

    def area_table(self) -> Table:
        table = Table([Column("area"), Column.number("MMBtu/y"), Column.number("t CO2e/y")])
        table.extend(self.by_area)
        return table

    def lines(self) -> list[str]:
        out = [self.headline, ""]
        out.extend(self.summary_lines())
        out.extend(["", "by trap", ""])
        out.extend(self.trap_table().lines())
        out.extend(["", "by area", ""])
        out.extend(self.area_table().lines())
        return out

    def as_dict(self) -> dict[str, object]:
        return {
            "reference": self.reference,
            "factor": self.factor,
            "kg_co2e_per_mmbtu": self.kg_per_mmbtu,
            "pounds_of_steam": round(self.steam.pounds, 1),
            "pounds_of_makeup": round(self.makeup_pounds, 1),
            "mmbtu": round(self.fuel.mmbtu, 2),
            "tonnes_co2e": round(self.tonnes_co2e, 3),
            "traps": [
                {
                    "tag": tag,
                    "condition": condition,
                    "pounds_per_year": pounds,
                    "mmbtu_per_year": mmbtu,
                    "tonnes_co2e": tonnes,
                }
                for tag, condition, pounds, mmbtu, tonnes in self.rows
            ],
            "by_area": [
                {"area": area, "mmbtu_per_year": mmbtu, "tonnes_co2e": tonnes}
                for area, mmbtu, tonnes in self.by_area
            ],
        }


def build_energy_report(register: LossRegister, top: int = 10) -> EnergyReport:
    losing = sorted(register.losing, key=lambda row: (-row.heat.mmbtu_per_year, str(row.tag)))
    by_area: dict[str, tuple[float, float]] = {}
    makeup = 0.0
    for row in register.rows:
        makeup += row.heat.makeup_water.pounds
        area = str(row.area)
        mmbtu, tonnes = by_area.get(area, (0.0, 0.0))
        by_area[area] = (
            mmbtu + row.heat.mmbtu_per_year,
            tonnes + row.stack.tonnes_co2e,
        )
    factor = register.rows[0].stack.factor if register.rows else None
    return EnergyReport(
        reference=register.reference,
        factor="none" if factor is None else factor.name,
        kg_per_mmbtu=0.0 if factor is None else factor.kg_co2e_per_mmbtu,
        steam=register.total_mass,
        fuel=register.total_fuel,
        tonnes_co2e=register.total_tonnes_co2e,
        makeup_pounds=makeup,
        rows=[
            (
                str(row.tag),
                row.condition.label,
                f"{row.steam.pounds_per_year:,.0f}",
                f"{row.heat.mmbtu_per_year:,.1f}",
                f"{row.stack.tonnes_co2e:,.2f}",
            )
            for row in losing[:top]
        ],
        by_area=[
            (area, f"{mmbtu:,.1f}", f"{tonnes:,.2f}")
            for area, (mmbtu, tonnes) in sorted(by_area.items())
        ],
    )
