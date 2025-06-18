"""From a verdict to pounds of steam a year, with the assumptions written down.

Every number in a loss register is a chain of assumptions, and the chain is
what gets challenged. So the estimate carries its own working: which orifice,
which discharge coefficient and why, what fraction of the seat was taken as
open, what back pressure was applied, and how many hours the leg is live.

The two that move the answer most are the least defensible. Orifice size comes
off the catalogue and is right. Open fraction comes off a condition code and is
a survey convention. Anybody reading the register is entitled to see that
distinction, so it is printed rather than buried.
"""

from __future__ import annotations

from dataclasses import dataclass

from dripleg.errors import ValidationError
from dripleg.loss.napier import SHARP_ORIFICE_CD, WORN_SEAT_CD, orifice_flow
from dripleg.model.installation import TrapInstallation
from dripleg.model.tags import TrapTag
from dripleg.survey.condition import TrapCondition
from dripleg.units.flow import Mass, MassFlow
from dripleg.units.pressure import Pressure

__all__ = ["SteamLoss", "estimate_steam_loss"]

# A seat that has been blowing for months is cut and rounded, so it passes
# more than a drilled hole of the same size. A seat that is only weeping is
# still close to square edged.
_COEFFICIENT_BY_CONDITION: dict[TrapCondition, float] = {
    TrapCondition.BLOWING_THROUGH: WORN_SEAT_CD,
    TrapCondition.LEAKING: SHARP_ORIFICE_CD,
    TrapCondition.RAPID_CYCLING: SHARP_ORIFICE_CD,
}


@dataclass(frozen=True)
class SteamLoss:
    """What one trap is losing, and everything that went into saying so."""

    tag: TrapTag
    condition: TrapCondition
    flow: MassFlow
    hours_per_year: float
    orifice_diameter_in: float
    open_fraction: float
    discharge_coefficient: float
    pressure: Pressure
    back_pressure: Pressure

    def __post_init__(self) -> None:
        if self.hours_per_year < 0:
            raise ValidationError("a year has no negative hours", field="hours_per_year")

    @property
    def is_losing(self) -> bool:
        return not self.flow.is_zero and self.hours_per_year > 0

    @property
    def annual_mass(self) -> Mass:
        return self.flow.over(self.hours_per_year)

    @property
    def pounds_per_year(self) -> float:
        return self.annual_mass.pounds

    def assumptions(self) -> list[str]:
        """The working, in the order somebody would challenge it."""

        return [
            f"orifice {self.orifice_diameter_in:.3f} in from the catalogue",
            f"{self.open_fraction:.0%} of the seat passing, from the {self.condition.label} code",
            f"discharge coefficient {self.discharge_coefficient:.2f}",
            f"{self.pressure} inlet against {self.back_pressure} discharge",
            f"{self.hours_per_year:,.0f} live hours a year",
        ]

    def __str__(self) -> str:
        if not self.is_losing:
            return f"{self.tag} losing nothing"
        return f"{self.tag} losing {self.flow} ({self.annual_mass} a year)"


def estimate_steam_loss(
    station: TrapInstallation,
    condition: TrapCondition,
    *,
    pressure: Pressure | None = None,
    open_fraction: float | None = None,
    hours_per_year: float | None = None,
) -> SteamLoss:
    """Steam through a failed seat, in pounds an hour and pounds a year.

    A condition that does not waste steam produces a zero loss rather than
    nothing at all, because a register with a row per trap is the one that can
    be added up and reconciled against the boiler.
    """

    inlet = pressure if pressure is not None else station.header.operating_pressure
    outlet = station.header.discharge_pressure
    if outlet.psia > inlet.psia:
        raise ValidationError(
            "the discharge pressure is above the measured inlet pressure",
            field="pressure",
        )
    fraction = open_fraction if open_fraction is not None else condition.severity_factor
    if not 0.0 <= fraction <= 1.0:
        raise ValidationError("the open fraction sits in [0, 1]", field="open_fraction")
    coefficient = _COEFFICIENT_BY_CONDITION.get(condition, SHARP_ORIFICE_CD)
    hours = hours_per_year if hours_per_year is not None else station.profile.annual_hours()
    flow = orifice_flow(
        inlet,
        station.model.orifice_diameter_in,
        downstream=outlet,
        discharge_coefficient=coefficient,
        open_fraction=fraction,
    )
    return SteamLoss(
        tag=station.tag,
        condition=condition,
        flow=flow,
        hours_per_year=hours,
        orifice_diameter_in=station.model.orifice_diameter_in,
        open_fraction=fraction,
        discharge_coefficient=coefficient,
        pressure=inlet,
        back_pressure=outlet,
    )
