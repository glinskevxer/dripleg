"""Reading the saturation table at a pressure that is not a row in it.

Interpolation is linear against the natural log of pressure rather than against
pressure itself. The saturation line is close to straight in log P and quite
bent in P, and the difference at a header sitting between two widely spaced
rows is a couple of degrees, which is enough to move a trap diagnosis.

The flash calculation lives here too, because it is the same table read twice.
Condensate at header pressure dropped into a lower pressure return line flashes
part of itself back to steam, and that flash is not a leak. Telling the two
apart is most of what a survey argument is about.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from dripleg.errors import ValidationError
from dripleg.steam.table import (
    SaturationPoint,
    row_bracketing_pressure,
    row_bracketing_temperature,
)
from dripleg.units.energy import SpecificEnthalpy
from dripleg.units.pressure import Pressure
from dripleg.units.temperature import Temperature

__all__ = [
    "FlashResult",
    "at_pressure",
    "at_temperature",
    "flash_at",
    "latent_heat_at",
    "saturation_pressure_at",
    "saturation_temperature_at",
]


def _blend(low: float, high: float, weight: float) -> float:
    return low + (high - low) * weight


def _weight_in_log_pressure(psia: float, low: SaturationPoint, high: SaturationPoint) -> float:
    if low is high:
        return 0.0
    span = math.log(high.pressure.psia) - math.log(low.pressure.psia)
    return (math.log(psia) - math.log(low.pressure.psia)) / span


def _interpolate(low: SaturationPoint, high: SaturationPoint, weight: float) -> SaturationPoint:
    if low is high or weight == 0.0:
        return low
    psia = math.exp(_blend(math.log(low.pressure.psia), math.log(high.pressure.psia), weight))
    hf = _blend(low.liquid_enthalpy.btu_per_pound, high.liquid_enthalpy.btu_per_pound, weight)
    hfg = _blend(low.latent_heat.btu_per_pound, high.latent_heat.btu_per_pound, weight)
    volume = math.exp(
        _blend(
            math.log(low.vapour_specific_volume),
            math.log(high.vapour_specific_volume),
            weight,
        )
    )
    return SaturationPoint(
        pressure=Pressure.from_psia(psia),
        temperature=Temperature.from_fahrenheit(
            _blend(low.temperature.fahrenheit, high.temperature.fahrenheit, weight)
        ),
        liquid_enthalpy=SpecificEnthalpy.from_btu_per_pound(hf),
        latent_heat=SpecificEnthalpy.from_btu_per_pound(hfg),
        vapour_enthalpy=SpecificEnthalpy.from_btu_per_pound(hf + hfg),
        vapour_specific_volume=volume,
    )


def at_pressure(pressure: Pressure) -> SaturationPoint:
    """The saturation state at an absolute pressure."""

    low, high = row_bracketing_pressure(pressure.psia)
    weight = _weight_in_log_pressure(pressure.psia, low, high)
    return _interpolate(low, high, weight)


def at_temperature(temperature: Temperature) -> SaturationPoint:
    """The saturation state at a temperature, the inverse lookup.

    Used to turn a pipe surface reading into the pressure the line must be at,
    which is how a header with no gauge on it gets a pressure at all.
    """

    low, high = row_bracketing_temperature(temperature.fahrenheit)
    if low is high:
        return low
    span = high.temperature.fahrenheit - low.temperature.fahrenheit
    weight = (temperature.fahrenheit - low.temperature.fahrenheit) / span
    return _interpolate(low, high, weight)


def saturation_temperature_at(pressure: Pressure) -> Temperature:
    return at_pressure(pressure).temperature


def saturation_pressure_at(temperature: Temperature) -> Pressure:
    return at_temperature(temperature).pressure


def latent_heat_at(pressure: Pressure) -> SpecificEnthalpy:
    return at_pressure(pressure).latent_heat


@dataclass(frozen=True)
class FlashResult:
    """What happens to a pound of condensate dropped to a lower pressure."""

    upstream: SaturationPoint
    downstream: SaturationPoint
    flash_fraction: float

    @property
    def liquid_fraction(self) -> float:
        return 1.0 - self.flash_fraction

    @property
    def percent(self) -> float:
        return self.flash_fraction * 100.0

    def flash_enthalpy(self) -> SpecificEnthalpy:
        """Heat carried away by the flash, per pound of condensate."""

        return SpecificEnthalpy.from_btu_per_pound(
            self.flash_fraction * self.downstream.latent_heat.btu_per_pound
        )


def flash_at(upstream: Pressure, downstream: Pressure) -> FlashResult:
    """Fraction of saturated condensate that flashes on the pressure drop.

    Straight heat balance: the liquid arrives carrying hf at the upstream
    pressure, and downstream it can only hold hf at the lower pressure, so the
    surplus boils off whatever fraction the latent heat down there will pay for.
    """

    if downstream.psia > upstream.psia:
        raise ValidationError(
            "condensate does not flash uphill, downstream pressure is the higher one",
            field="pressure",
        )
    hot = at_pressure(upstream)
    cold = at_pressure(downstream)
    surplus = hot.liquid_enthalpy.btu_per_pound - cold.liquid_enthalpy.btu_per_pound
    fraction = surplus / cold.latent_heat.btu_per_pound
    fraction = min(max(fraction, 0.0), 1.0)
    return FlashResult(upstream=hot, downstream=cold, flash_fraction=fraction)
