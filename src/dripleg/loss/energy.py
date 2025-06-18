"""How much heat a pound of lost steam actually costs, which is not one number.

A trap venting to atmosphere loses everything: the heat that boiled the water,
and the water. A trap blowing into a closed return line feels like it should
lose much less, and this is the assumption that gets a survey argued with.

It does not. The steam condenses in the return line and the condensate goes
back to the deaerator, but the heat that comes back with it is the sensible
heat of hot water, twenty odd Btu a pound above the feedwater it displaces. The
latent heat, which is nine hundred odd Btu a pound and the entire reason the
boiler was fired, is given up in the return line where nothing uses it. And
live steam in a return line overwhelms the receiver, so a share of it goes
straight out of the vent along with the water.

So a closed return failure costs nearly what a vented one costs. The credit is
real and it is small, and this module works it out rather than assuming it
either way.

The fuel number is the heat divided by boiler efficiency, and it is the one
that goes on the invoice. Nobody buys enthalpy.
"""

from __future__ import annotations

from dataclasses import dataclass

from dripleg.errors import ValidationError
from dripleg.loss.estimate import SteamLoss
from dripleg.model.installation import TrapInstallation
from dripleg.steam.saturated import at_pressure
from dripleg.units.energy import Energy, SpecificEnthalpy
from dripleg.units.flow import Mass
from dripleg.units.temperature import Temperature

__all__ = ["EnergyModel", "HeatLoss"]

_BTU_PER_LB_PER_F = 1.0


@dataclass(frozen=True)
class EnergyModel:
    """What the boiler house costs, as far as a trap survey needs to know."""

    feedwater_temperature: Temperature
    boiler_efficiency: float = 0.82
    condensate_returned: float = 0.75
    receiver_vent_fraction: float = 0.35

    def __post_init__(self) -> None:
        if not 0.0 < self.boiler_efficiency <= 1.0:
            raise ValidationError("boiler efficiency sits in (0, 1]", field="boiler_efficiency")
        if not 0.0 <= self.condensate_returned <= 1.0:
            raise ValidationError(
                "the returned condensate fraction sits in [0, 1]", field="condensate_returned"
            )
        if not 0.0 <= self.receiver_vent_fraction <= 1.0:
            raise ValidationError(
                "the receiver vent fraction sits in [0, 1]", field="receiver_vent_fraction"
            )

    @classmethod
    def typical(cls) -> EnergyModel:
        """A deaerator at 227 F on a plant with most of its condensate back."""

        return cls(feedwater_temperature=Temperature.from_fahrenheit(227.0))

    def feedwater_enthalpy(self) -> SpecificEnthalpy:
        """Heat already in the makeup, above 32 F, to one Btu per degree."""

        return SpecificEnthalpy.from_btu_per_pound(
            (self.feedwater_temperature.fahrenheit - 32.0) * _BTU_PER_LB_PER_F
        )

    def heat_per_pound(self, station: TrapInstallation, loss: SteamLoss) -> SpecificEnthalpy:
        """Heat lost for each pound of steam through the seat.

        Open discharge is the whole enthalpy above the feedwater it has to be
        replaced with. A closed return splits three ways: the share the
        receiver vents is a total loss, the share that condenses and comes back
        is credited with the condensate's sensible heat, and the share that
        condenses and is dumped is a total loss again.
        """

        steam = at_pressure(loss.pressure).vapour_enthalpy
        feedwater = self.feedwater_enthalpy()
        total = (steam - feedwater).btu_per_pound
        if not station.discharge_destination.condensate_is_recovered:
            return SpecificEnthalpy.from_btu_per_pound(total)
        condensate = at_pressure(station.header.discharge_pressure).liquid_enthalpy
        credited = (steam - condensate).btu_per_pound
        vented = self.receiver_vent_fraction
        condensed = 1.0 - vented
        per_pound = (
            vented * total
            + condensed * self.condensate_returned * credited
            + condensed * (1.0 - self.condensate_returned) * total
        )
        return SpecificEnthalpy.from_btu_per_pound(per_pound)

    def water_lost_per_pound(self, station: TrapInstallation) -> float:
        """Pounds of makeup water needed per pound of steam through the seat."""

        if not station.discharge_destination.condensate_is_recovered:
            return 1.0
        kept = (1.0 - self.receiver_vent_fraction) * self.condensate_returned
        return 1.0 - kept

    def assess(self, station: TrapInstallation, loss: SteamLoss) -> HeatLoss:
        per_pound = self.heat_per_pound(station, loss)
        return HeatLoss(
            loss=loss,
            heat_per_pound=per_pound,
            annual_heat=per_pound.carried_by(loss.annual_mass),
            makeup_water=Mass.from_pounds(
                loss.annual_mass.pounds * self.water_lost_per_pound(station)
            ),
            recovered=station.discharge_destination.condensate_is_recovered,
            boiler_efficiency=self.boiler_efficiency,
        )


@dataclass(frozen=True)
class HeatLoss:
    """One trap's loss, once the boiler house has been taken into account."""

    loss: SteamLoss
    heat_per_pound: SpecificEnthalpy
    annual_heat: Energy
    makeup_water: Mass
    recovered: bool
    boiler_efficiency: float

    @property
    def annual_fuel(self) -> Energy:
        return self.annual_heat.divided_by_efficiency(self.boiler_efficiency)

    @property
    def mmbtu_per_year(self) -> float:
        return self.annual_fuel.mmbtu

    @property
    def destination_note(self) -> str:
        if self.recovered:
            return "into a closed return, so the condensate that comes back is credited"
        return "to atmosphere, so the heat and the water are both gone"

    def __str__(self) -> str:
        return (
            f"{self.loss.tag} {self.mmbtu_per_year:,.1f} MMBtu of fuel a year, "
            f"{self.makeup_water.pounds:,.0f} lb of makeup"
        )
