"""What the lost steam is worth, in money somebody can sign off.

Three bills, and only the first one ever gets quoted.

Fuel is the big one and everybody costs it. Water is small per pound and adds
up on a plant venting steam all year, and it is two bills rather than one,
because water that comes in is paid for at the meter and water that leaves is
paid for again at the effluent charge. Treatment chemical goes with the makeup
and is the one that surprises people, because it is priced per thousand gallons
of makeup and a blowing trap makes a lot of makeup.

Everything lands as whole cents through the price type, so the register adds up
the same way twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from dripleg.errors import ValidationError
from dripleg.loss.energy import HeatLoss
from dripleg.units.flow import Mass
from dripleg.units.money import Money, Price

__all__ = ["POUNDS_PER_GALLON", "CostBasis", "LossCost"]

POUNDS_PER_GALLON = 8.3378
"""Water at boiler house temperatures, near enough for a makeup bill."""


def _thousand_gallons(mass: Mass) -> Decimal:
    return Decimal(str(mass.pounds / POUNDS_PER_GALLON / 1000.0))


@dataclass(frozen=True)
class CostBasis:
    """The prices a site is actually paying this year."""

    fuel: Price
    water: Price
    effluent: Price
    chemical: Price

    def __post_init__(self) -> None:
        if self.fuel.unit.lower() not in {"mmbtu", "dth"}:
            raise ValidationError("fuel is priced per MMBtu here", field="fuel")
        for name in ("water", "effluent", "chemical"):
            price: Price = getattr(self, name)
            if "gal" not in price.unit.lower():
                raise ValidationError(f"{name} is priced per thousand gallons", field=name)

    @classmethod
    def typical(cls) -> CostBasis:
        """Prices in the region of what a mill pays, for a worked example."""

        return cls(
            fuel=Price.of("6.25", "MMBtu"),
            water=Price.of("4.10", "1000 gal"),
            effluent=Price.of("3.40", "1000 gal"),
            chemical=Price.of("2.75", "1000 gal"),
        )

    def cost_of(self, heat: HeatLoss) -> LossCost:
        thousands = _thousand_gallons(heat.makeup_water)
        return LossCost(
            heat=heat,
            fuel=self.fuel.times(Decimal(str(heat.annual_fuel.mmbtu))),
            water=self.water.times(thousands),
            effluent=self.effluent.times(thousands),
            chemical=self.chemical.times(thousands),
        )


@dataclass(frozen=True)
class LossCost:
    """One trap's annual bill, split so it can be argued with line by line."""

    heat: HeatLoss
    fuel: Money
    water: Money
    effluent: Money
    chemical: Money

    @property
    def water_side(self) -> Money:
        return self.water + self.effluent + self.chemical

    @property
    def total(self) -> Money:
        return self.fuel + self.water_side

    @property
    def is_free(self) -> bool:
        return self.total.is_zero

    @property
    def fuel_share(self) -> float:
        if self.total.cents == 0:
            return 0.0
        return self.fuel.cents / self.total.cents

    @property
    def tag(self) -> str:
        return str(self.heat.loss.tag)

    def lines(self) -> list[tuple[str, Money]]:
        return [
            ("fuel", self.fuel),
            ("makeup water", self.water),
            ("effluent", self.effluent),
            ("treatment chemical", self.chemical),
            ("total", self.total),
        ]

    def __str__(self) -> str:
        return f"{self.tag} {self.total} a year"
