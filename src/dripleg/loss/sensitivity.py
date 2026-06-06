"""How far the answer moves when the assumptions move, one at a time.

Every loss figure rests on six numbers and only two of them are measured. The
orifice comes off the catalogue and is right. The header pressure is measured
or taken off the register and is close. The other four are conventions: what
fraction of the seat is open, what the discharge coefficient is, how many hours
the leg is live, and what a boiler costs to run.

An engineer who does not know which of those the answer is sensitive to cannot
argue with the answer sensibly, and will usually argue with the wrong one. So
this moves each of them across its plausible range on its own and reports the
swing, which turns "your numbers are made up" into a conversation about the two
that actually matter.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from dripleg.errors import ValidationError
from dripleg.loss.cost import CostBasis
from dripleg.loss.emissions import EmissionsFactor, StackLoss
from dripleg.loss.energy import EnergyModel
from dripleg.loss.estimate import estimate_steam_loss
from dripleg.model.installation import TrapInstallation
from dripleg.survey.condition import TrapCondition
from dripleg.units.money import Money

__all__ = ["Sensitivity", "Swing", "sweep"]


@dataclass(frozen=True)
class Swing:
    """One assumption moved across its range, and what that did."""

    assumption: str
    low_label: str
    high_label: str
    low_cost: Money
    base_cost: Money
    high_cost: Money

    @property
    def spread(self) -> Money:
        return self.high_cost - self.low_cost

    @property
    def share_of_base(self) -> float:
        if self.base_cost.cents == 0:
            return 0.0
        return abs(self.spread.cents) / self.base_cost.cents

    def __str__(self) -> str:
        return (
            f"{self.assumption}: {self.low_label} gives {self.low_cost}, "
            f"{self.high_label} gives {self.high_cost}"
        )


@dataclass(frozen=True)
class Sensitivity:
    """Every assumption swept, worst first."""

    tag: str
    base_cost: Money
    swings: list[Swing]

    @property
    def worst(self) -> Swing | None:
        return self.swings[0] if self.swings else None

    def named(self, assumption: str) -> Swing | None:
        for swing in self.swings:
            if swing.assumption == assumption:
                return swing
        return None

    @property
    def widest_share(self) -> float:
        return 0.0 if not self.swings else self.swings[0].share_of_base

    def __str__(self) -> str:
        if not self.swings:
            return f"{self.tag} loses nothing, so nothing moves it"
        worst = self.swings[0]
        return (
            f"{self.tag} at {self.base_cost}, most sensitive to {worst.assumption} "
            f"({worst.share_of_base:.0%})"
        )


def _cost(
    station: TrapInstallation,
    condition: TrapCondition,
    energy: EnergyModel,
    prices: CostBasis,
    factor: EmissionsFactor,
    *,
    open_fraction: float | None = None,
    hours: float | None = None,
) -> Money:
    steam = estimate_steam_loss(
        station, condition, open_fraction=open_fraction, hours_per_year=hours
    )
    heat = energy.assess(station, steam)
    StackLoss(heat=heat, factor=factor)
    return prices.cost_of(heat).total


def sweep(
    station: TrapInstallation,
    condition: TrapCondition,
    energy: EnergyModel,
    prices: CostBasis,
    factor: EmissionsFactor,
) -> Sensitivity:
    """Move each convention across its range on its own."""

    if not condition.wastes_steam:
        return Sensitivity(tag=str(station.tag), base_cost=Money.zero(), swings=[])
    base = _cost(station, condition, energy, prices, factor)
    if base.cents == 0:
        raise ValidationError(
            "a wasting condition should cost something before it is swept",
            field="condition",
        )
    hours = station.profile.annual_hours()
    swings = [
        Swing(
            assumption="open fraction of the seat",
            low_label="half the convention",
            high_label="the whole seat",
            low_cost=_cost(
                station,
                condition,
                energy,
                prices,
                factor,
                open_fraction=condition.severity_factor / 2,
            ),
            base_cost=base,
            high_cost=_cost(station, condition, energy, prices, factor, open_fraction=1.0),
        ),
        Swing(
            assumption="live hours a year",
            low_label="half a year",
            high_label="every hour",
            low_cost=_cost(station, condition, energy, prices, factor, hours=hours / 2),
            base_cost=base,
            high_cost=_cost(station, condition, energy, prices, factor, hours=8760.0),
        ),
        Swing(
            assumption="boiler efficiency",
            low_label="70 per cent",
            high_label="90 per cent",
            low_cost=_cost(
                station, condition, replace(energy, boiler_efficiency=0.90), prices, factor
            ),
            base_cost=base,
            high_cost=_cost(
                station, condition, replace(energy, boiler_efficiency=0.70), prices, factor
            ),
        ),
        Swing(
            assumption="condensate returned",
            low_label="all of it",
            high_label="none of it",
            low_cost=_cost(
                station, condition, replace(energy, condensate_returned=1.0), prices, factor
            ),
            base_cost=base,
            high_cost=_cost(
                station, condition, replace(energy, condensate_returned=0.0), prices, factor
            ),
        ),
        Swing(
            assumption="fuel price",
            low_label="half",
            high_label="double",
            low_cost=base.scaled(0.5),
            base_cost=base,
            high_cost=base.scaled(2.0),
        ),
    ]
    return Sensitivity(
        tag=str(station.tag),
        base_cost=base,
        swings=sorted(swings, key=lambda swing: (-swing.share_of_base, swing.assumption)),
    )
