"""The loss register: one row per trap, and the totals that come off it.

Every trap gets a row, including the ones losing nothing. That is not padding.
A register with only the failures in it cannot be reconciled against anything,
cannot show a year on year improvement, and cannot answer the first question a
sceptical engineer asks, which is how many traps you looked at to find these.

The rows carry the whole chain from verdict to money, so any number in a
summary can be walked back to the reading that produced it.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from dripleg.diagnosis.batch import SurveyDiagnosis
from dripleg.diagnosis.engine import Diagnosis
from dripleg.loss.cost import CostBasis, LossCost
from dripleg.loss.emissions import EmissionsFactor, StackLoss
from dripleg.loss.energy import EnergyModel, HeatLoss
from dripleg.loss.estimate import SteamLoss, estimate_steam_loss
from dripleg.model.attributes import ServiceType
from dripleg.model.installation import TrapInstallation
from dripleg.model.register import TrapRegister
from dripleg.model.tags import AreaCode, TrapTag
from dripleg.survey.condition import TrapCondition
from dripleg.units.energy import Energy
from dripleg.units.flow import Mass, MassFlow
from dripleg.units.money import Money

__all__ = ["LossRegister", "TrapLoss", "build_loss_register"]


@dataclass(frozen=True)
class TrapLoss:
    """One row: the verdict, the steam, the heat, the money and the stack."""

    station: TrapInstallation
    diagnosis: Diagnosis
    steam: SteamLoss
    heat: HeatLoss
    cost: LossCost
    stack: StackLoss

    @property
    def tag(self) -> TrapTag:
        return self.station.tag

    @property
    def area(self) -> AreaCode:
        return self.station.tag.area

    @property
    def service(self) -> ServiceType:
        return self.station.service

    @property
    def condition(self) -> TrapCondition:
        return self.diagnosis.condition

    @property
    def is_losing(self) -> bool:
        return self.steam.is_losing

    @property
    def annual_cost(self) -> Money:
        return self.cost.total

    def __str__(self) -> str:
        if not self.is_losing:
            return f"{self.tag} {self.condition.label}, nothing lost"
        return f"{self.tag} {self.condition.label}, {self.annual_cost} a year"


class LossRegister:
    """Every row from one survey, and the arithmetic over them."""

    def __init__(self, reference: str, rows: list[TrapLoss]) -> None:
        self.reference = reference
        self.rows = sorted(rows, key=lambda r: r.tag)

    def __len__(self) -> int:
        return len(self.rows)

    def __iter__(self) -> Iterator[TrapLoss]:
        return iter(self.rows)

    @property
    def losing(self) -> list[TrapLoss]:
        return [row for row in self.rows if row.is_losing]

    @property
    def total_flow(self) -> MassFlow:
        total = MassFlow.zero()
        for row in self.rows:
            total = total + row.steam.flow
        return total

    @property
    def total_mass(self) -> Mass:
        return Mass.from_pounds(sum(row.steam.pounds_per_year for row in self.rows))

    @property
    def total_fuel(self) -> Energy:
        return Energy.from_btu(sum(row.heat.annual_fuel.btu for row in self.rows))

    @property
    def total_cost(self) -> Money:
        total = Money.zero()
        for row in self.rows:
            total = total + row.annual_cost
        return total

    @property
    def total_tonnes_co2e(self) -> float:
        return sum(row.stack.tonnes_co2e for row in self.rows)

    @property
    def loss_rate(self) -> float:
        if not self.rows:
            return 0.0
        return len(self.losing) / len(self.rows)

    def top_losers(self, count: int = 10) -> list[TrapLoss]:
        return sorted(self.losing, key=lambda r: (-r.annual_cost.cents, r.tag))[:count]

    def cost_by_area(self) -> dict[AreaCode, Money]:
        totals: dict[AreaCode, Money] = {}
        for row in self.rows:
            totals[row.area] = totals.get(row.area, Money.zero()) + row.annual_cost
        return dict(sorted(totals.items()))

    def cost_by_service(self) -> dict[ServiceType, Money]:
        totals: dict[ServiceType, Money] = {}
        for row in self.rows:
            totals[row.service] = totals.get(row.service, Money.zero()) + row.annual_cost
        return dict(sorted(totals.items(), key=lambda pair: -pair[1].cents))

    def cost_by_condition(self) -> dict[TrapCondition, Money]:
        totals: dict[TrapCondition, Money] = {}
        for row in self.rows:
            totals[row.condition] = totals.get(row.condition, Money.zero()) + row.annual_cost
        return dict(sorted(totals.items(), key=lambda pair: pair[0].rank))

    def find(self, tag: TrapTag | str) -> TrapLoss | None:
        wanted = tag if isinstance(tag, TrapTag) else TrapTag.parse(tag)
        for row in self.rows:
            if row.tag == wanted:
                return row
        return None

    def share_of_total(self, row: TrapLoss) -> float:
        total = self.total_cost.cents
        if total == 0:
            return 0.0
        return row.annual_cost.cents / total

    def __str__(self) -> str:
        return (
            f"{self.reference}: {len(self.losing)} of {len(self.rows)} losing, "
            f"{self.total_cost} a year"
        )


def build_loss_register(
    register: TrapRegister,
    diagnosis: SurveyDiagnosis,
    energy: EnergyModel,
    prices: CostBasis,
    factor: EmissionsFactor,
) -> LossRegister:
    """Cost every verdict from one survey."""

    rows: list[TrapLoss] = []
    for verdict in diagnosis.results:
        station = register.find(verdict.tag)
        if station is None:
            continue
        steam = estimate_steam_loss(station, verdict.condition)
        heat = energy.assess(station, steam)
        rows.append(
            TrapLoss(
                station=station,
                diagnosis=verdict,
                steam=steam,
                heat=heat,
                cost=prices.cost_of(heat),
                stack=StackLoss(heat=heat, factor=factor),
            )
        )
    return LossRegister(diagnosis.reference, rows)
