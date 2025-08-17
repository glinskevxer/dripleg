"""The loss register, rendered, and the two numbers people actually quote.

The two are the annual total and the top ten. The total settles whether the
programme is worth running at all, and the top ten is what gets acted on this
month, because a crew can do ten jobs and cannot do four hundred.

Under both is the share table, which is the one that changes minds. On every
survey this has been run against, something like a fifth of the failed traps
carry three quarters of the money, and seeing that written down is what stops a
plant spreading the budget evenly across the register.
"""

from __future__ import annotations

from dataclasses import dataclass

from dripleg.loss.register import LossRegister
from dripleg.report.table import Column, Table
from dripleg.units.money import Money

__all__ = ["LossReport", "build_loss_report"]

TOP_COUNT = 10


@dataclass(frozen=True)
class LossReport:
    """A costed survey, ready to print."""

    reference: str
    traps: int
    losing: int
    pounds_per_hour: float
    pounds_per_year: float
    mmbtu_per_year: float
    tonnes_co2e: float
    total_cost: Money
    top: list[tuple[str, str, str, str]]
    by_area: list[tuple[str, str, str]]
    by_condition: list[tuple[str, str, str]]

    @property
    def loss_rate(self) -> float:
        if self.traps == 0:
            return 0.0
        return self.losing / self.traps

    @property
    def headline(self) -> str:
        return (
            f"{self.reference}: {self.losing} of {self.traps} traps losing {self.total_cost} a year"
        )

    def summary_lines(self) -> list[str]:
        return [
            f"traps            {self.traps}",
            f"losing steam     {self.losing} ({self.loss_rate:.1%})",
            f"steam lost       {self.pounds_per_hour:,.1f} lb/h, "
            f"{self.pounds_per_year:,.0f} lb a year",
            f"fuel             {self.mmbtu_per_year:,.1f} MMBtu a year",
            f"carbon           {self.tonnes_co2e:,.1f} t CO2e a year",
            f"annual cost      {self.total_cost}",
        ]

    def top_table(self) -> Table:
        table = Table(
            [
                Column("tag"),
                Column("condition"),
                Column.number("lb/h"),
                Column.number("a year"),
            ]
        )
        table.extend(self.top)
        return table

    def area_table(self) -> Table:
        table = Table([Column("area"), Column.number("a year"), Column.number("share")])
        table.extend(self.by_area)
        return table

    def condition_table(self) -> Table:
        table = Table([Column("condition"), Column.number("a year"), Column.number("share")])
        table.extend(self.by_condition)
        return table

    def lines(self) -> list[str]:
        out = [self.headline, ""]
        out.extend(self.summary_lines())
        out.extend(["", f"the {len(self.top)} dearest traps", ""])
        out.extend(self.top_table().lines())
        out.extend(["", "by area", ""])
        out.extend(self.area_table().lines())
        out.extend(["", "by condition", ""])
        out.extend(self.condition_table().lines())
        return out

    def render(self) -> str:
        return "\n".join(self.lines())

    def as_dict(self) -> dict[str, object]:
        return {
            "reference": self.reference,
            "traps": self.traps,
            "losing": self.losing,
            "loss_rate": round(self.loss_rate, 4),
            "pounds_per_hour": round(self.pounds_per_hour, 2),
            "pounds_per_year": round(self.pounds_per_year, 1),
            "mmbtu_per_year": round(self.mmbtu_per_year, 2),
            "tonnes_co2e": round(self.tonnes_co2e, 3),
            "annual_cost_cents": self.total_cost.cents,
            "top": [
                {"tag": tag, "condition": condition, "pounds_per_hour": flow, "annual": cost}
                for tag, condition, flow, cost in self.top
            ],
            "by_area": [
                {"area": area, "annual": cost, "share": share} for area, cost, share in self.by_area
            ],
            "by_condition": [
                {"condition": condition, "annual": cost, "share": share}
                for condition, cost, share in self.by_condition
            ],
        }


def _share(part: Money, whole: Money) -> str:
    if whole.cents == 0:
        return "0.0%"
    return f"{part.cents / whole.cents:.1%}"


def build_loss_report(register: LossRegister, top: int = TOP_COUNT) -> LossReport:
    total = register.total_cost
    return LossReport(
        reference=register.reference,
        traps=len(register),
        losing=len(register.losing),
        pounds_per_hour=register.total_flow.pounds_per_hour,
        pounds_per_year=register.total_mass.pounds,
        mmbtu_per_year=register.total_fuel.mmbtu,
        tonnes_co2e=register.total_tonnes_co2e,
        total_cost=total,
        top=[
            (
                str(row.tag),
                row.condition.label,
                f"{row.steam.flow.pounds_per_hour:,.1f}",
                str(row.annual_cost),
            )
            for row in register.top_losers(top)
        ],
        by_area=[
            (str(area), str(cost), _share(cost, total))
            for area, cost in register.cost_by_area().items()
        ],
        by_condition=[
            (condition.label, str(cost), _share(cost, total))
            for condition, cost in register.cost_by_condition().items()
        ],
    )
