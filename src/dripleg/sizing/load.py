"""Condensate load on a steam main, which is two very different numbers.

Warm-up load is what the line makes while it is coming up to temperature from
cold: the steel has to be heated, and every pound of steel takes about a ninth
of a Btu per degree. On a long cold main that is an enormous load for a short
time, and it is the number a drip trap has to be sized for, because a trap
sized for the running load floods the main on start up and the main then tries
to carry water at fifty miles an hour.

Running load is what the line makes once it is hot: the standing heat loss
through the insulation, condensing steam at the rate the lagging leaks heat. It
is small, steady, and the number people size traps for by mistake.

Both come out here in pounds an hour so the sizing check can hold them against
what the fitted trap will pass.
"""

from __future__ import annotations

from dataclasses import dataclass

from dripleg.errors import OutOfRangeError, ValidationError
from dripleg.steam.saturated import at_pressure
from dripleg.units.flow import MassFlow
from dripleg.units.pressure import Pressure
from dripleg.units.temperature import Temperature

__all__ = [
    "BARE_PIPE_COEFFICIENT",
    "PIPE_SIZES",
    "PipeSize",
    "STEEL_SPECIFIC_HEAT",
    "pipe_size",
    "running_load",
    "warmup_load",
]

STEEL_SPECIFIC_HEAT = 0.114
"""Btu per pound per degree F, carbon steel, near enough over this range."""

BARE_PIPE_COEFFICIENT = 2.1
"""Btu per hour per square foot per degree F off bare horizontal pipe in still air."""

DEFAULT_INSULATION_EFFICIENCY = 0.85

# A safety factor on warm-up, because a main does not warm evenly and the trap
# sees the worst of it. Two is the number the survey standard here works to.
WARMUP_SAFETY_FACTOR = 2.0


@dataclass(frozen=True)
class PipeSize:
    """One nominal pipe size, schedule 40."""

    nominal: str
    outside_diameter_in: float
    weight_lb_per_ft: float

    def __post_init__(self) -> None:
        if self.outside_diameter_in <= 0 or self.weight_lb_per_ft <= 0:
            raise ValidationError("a pipe has a diameter and a weight", field="pipe")

    @property
    def surface_ft2_per_ft(self) -> float:
        """Outside surface area of one foot of pipe."""

        return 3.141592653589793 * self.outside_diameter_in / 12.0


_ROWS: tuple[tuple[str, float, float], ...] = (
    ("1/2", 0.840, 0.85),
    ("3/4", 1.050, 1.13),
    ("1", 1.315, 1.68),
    ("1-1/4", 1.660, 2.27),
    ("1-1/2", 1.900, 2.72),
    ("2", 2.375, 3.65),
    ("2-1/2", 2.875, 5.79),
    ("3", 3.500, 7.58),
    ("4", 4.500, 10.79),
    ("6", 6.625, 18.97),
    ("8", 8.625, 28.55),
    ("10", 10.750, 40.48),
    ("12", 12.750, 49.56),
)

PIPE_SIZES: dict[str, PipeSize] = {
    nominal: PipeSize(nominal=nominal, outside_diameter_in=od, weight_lb_per_ft=weight)
    for nominal, od, weight in _ROWS
}


def pipe_size(nominal: str) -> PipeSize:
    key = nominal.strip().replace(" ", "").replace('"', "")
    try:
        return PIPE_SIZES[key]
    except KeyError:
        known = ", ".join(PIPE_SIZES)
        raise ValidationError(
            f"{nominal!r} is not a pipe size this build carries, expected one of: {known}",
            field="pipe",
        ) from None


def _check(length_ft: float, ambient: Temperature, saturation: Temperature) -> None:
    if length_ft <= 0:
        raise ValidationError("a run of pipe has a length", field="length_ft")
    if ambient >= saturation:
        raise OutOfRangeError(
            "the air is at or above the steam temperature, so nothing condenses",
            field="ambient",
            value=ambient.fahrenheit,
            high=saturation.fahrenheit,
        )


def warmup_load(
    pipe: PipeSize,
    length_ft: float,
    pressure: Pressure,
    ambient: Temperature,
    *,
    minutes: float = 30.0,
    safety_factor: float = WARMUP_SAFETY_FACTOR,
) -> MassFlow:
    """Condensate made bringing a cold run up to temperature.

    Heat into the steel divided by the latent heat, spread over the warm-up
    time, then multiplied by the safety factor the standard applies.
    """

    if minutes <= 0:
        raise ValidationError("a warm up takes some time", field="minutes")
    if safety_factor < 1.0:
        raise ValidationError("a safety factor is at least one", field="safety_factor")
    point = at_pressure(pressure)
    _check(length_ft, ambient, point.temperature)
    steel = pipe.weight_lb_per_ft * length_ft
    rise = point.temperature.fahrenheit - ambient.fahrenheit
    heat = steel * STEEL_SPECIFIC_HEAT * rise
    pounds = heat / point.latent_heat.btu_per_pound
    return MassFlow.from_pounds_per_hour(pounds / (minutes / 60.0) * safety_factor)


def running_load(
    pipe: PipeSize,
    length_ft: float,
    pressure: Pressure,
    ambient: Temperature,
    *,
    insulated: bool = True,
    insulation_efficiency: float = DEFAULT_INSULATION_EFFICIENCY,
) -> MassFlow:
    """Condensate made by a hot line standing still.

    Surface area times the film coefficient times the temperature difference,
    knocked down by whatever the lagging is doing, over the latent heat.
    """

    if not 0.0 <= insulation_efficiency < 1.0:
        raise ValidationError("insulation efficiency sits in [0, 1)", field="insulation_efficiency")
    point = at_pressure(pressure)
    _check(length_ft, ambient, point.temperature)
    area = pipe.surface_ft2_per_ft * length_ft
    difference = point.temperature.fahrenheit - ambient.fahrenheit
    heat = area * BARE_PIPE_COEFFICIENT * difference
    if insulated:
        heat *= 1.0 - insulation_efficiency
    return MassFlow.from_pounds_per_hour(heat / point.latent_heat.btu_per_pound)
