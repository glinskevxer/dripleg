"""What the lost fuel puts up the stack.

This exists because the number goes on a different report to a different
person, and because that person's question is not the plant manager's. The
plant manager wants the annual bill. The person compiling the site's carbon
figures wants tonnes, wants to know whether it is combustion or purchased
energy, and wants the factor written next to the answer so it can be swapped
when the published one changes.

So the factor is data, dated, with a source string on it, and the calculation
is one multiplication that nobody has to go looking for.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from dripleg.errors import ValidationError
from dripleg.loss.energy import HeatLoss
from dripleg.units.energy import Energy

__all__ = ["EmissionsFactor", "FACTORS", "StackLoss", "factor_named"]

_KG_PER_TONNE = 1000.0


@dataclass(frozen=True)
class EmissionsFactor:
    """Kilograms of carbon dioxide equivalent per MMBtu of fuel burned."""

    name: str
    kg_co2e_per_mmbtu: float
    source: str
    published: dt.date

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValidationError("an emissions factor needs a name", field="name")
        if self.kg_co2e_per_mmbtu <= 0:
            raise ValidationError("an emissions factor is positive", field="kg_co2e_per_mmbtu")
        if not self.source.strip():
            raise ValidationError("say where the factor came from", field="source")

    def applied_to(self, fuel: Energy) -> float:
        """Tonnes of carbon dioxide equivalent for that much fuel."""

        return fuel.mmbtu * self.kg_co2e_per_mmbtu / _KG_PER_TONNE

    @property
    def is_stale(self) -> bool:
        """Published factors get revised. Four years is long enough to check."""

        return (dt.date.today() - self.published).days > 4 * 365

    def __str__(self) -> str:
        return f"{self.name} {self.kg_co2e_per_mmbtu:.1f} kg/MMBtu ({self.published})"


FACTORS: dict[str, EmissionsFactor] = {
    "natural_gas": EmissionsFactor(
        name="natural gas",
        kg_co2e_per_mmbtu=53.1,
        source="site fuel contract heat content and the national grid factor",
        published=dt.date(2024, 4, 1),
    ),
    "fuel_oil_2": EmissionsFactor(
        name="number 2 fuel oil",
        kg_co2e_per_mmbtu=73.5,
        source="site fuel contract heat content and the national grid factor",
        published=dt.date(2024, 4, 1),
    ),
    "coal": EmissionsFactor(
        name="bituminous coal",
        kg_co2e_per_mmbtu=93.3,
        source="site fuel contract heat content and the national grid factor",
        published=dt.date(2024, 4, 1),
    ),
    "biomass": EmissionsFactor(
        name="wood residue",
        kg_co2e_per_mmbtu=8.4,
        source="non biogenic share only, site fuel contract",
        published=dt.date(2024, 4, 1),
    ),
}


def factor_named(name: str) -> EmissionsFactor:
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    try:
        return FACTORS[key]
    except KeyError:
        known = ", ".join(sorted(FACTORS))
        raise ValidationError(
            f"{name!r} is not a fuel this build has a factor for, expected one of: {known}",
            field="fuel",
        ) from None


@dataclass(frozen=True)
class StackLoss:
    """One trap's annual emissions, with the factor that produced them."""

    heat: HeatLoss
    factor: EmissionsFactor

    @property
    def tonnes_co2e(self) -> float:
        return self.factor.applied_to(self.heat.annual_fuel)

    @property
    def kilograms_co2e(self) -> float:
        return self.tonnes_co2e * _KG_PER_TONNE

    @property
    def is_material(self) -> bool:
        """Whether this one trap is worth naming in a carbon report."""

        return self.tonnes_co2e >= 1.0

    def __str__(self) -> str:
        return (
            f"{self.heat.loss.tag} {self.tonnes_co2e:,.2f} t CO2e a year "
            f"on the {self.factor.name} factor"
        )
