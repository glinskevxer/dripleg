"""What a trap will actually pass, and whether that suits what it is draining.

A trap orifice passing condensate is an orifice passing a liquid, which is a
completely different sum to the same orifice passing steam. Both matter and
they are easy to confuse: the steam number is what a failed trap loses and the
condensate number is what a working one can get rid of.

Oversizing is the failure nobody reports. A trap four times too big works
perfectly, passes every survey, and wears its seat out in eighteen months
because it never fills and so cycles on steam rather than water. A survey that
only reports failures will find that trap again and again and never say why.

So the sizing check runs on the traps that passed, not the ones that failed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from dripleg.errors import ValidationError
from dripleg.model.catalogue import TrapModel
from dripleg.units.flow import MassFlow
from dripleg.units.pressure import Pressure
from dripleg.units.temperature import Temperature

__all__ = [
    "ORIFICE_CONSTANT",
    "SizingVerdict",
    "SizingCheck",
    "check_sizing",
    "condensate_capacity",
    "condensate_density",
]

ORIFICE_CONSTANT = 2406.0
"""Pounds an hour per square inch per root psi per root pound per cubic foot."""

# Saturated water density in pounds per cubic foot, against temperature.
_DENSITY: tuple[tuple[float, float], ...] = (
    (60.0, 62.36),
    (100.0, 61.99),
    (150.0, 61.18),
    (212.0, 59.81),
    (250.0, 58.82),
    (300.0, 57.31),
    (350.0, 55.59),
    (400.0, 53.65),
    (450.0, 51.44),
    (500.0, 48.95),
)

DEFAULT_SAFETY_FACTOR = 2.0
OVERSIZE_LIMIT = 5.0


def condensate_density(temperature: Temperature) -> float:
    """Saturated water density, interpolated between the table rows."""

    degrees = temperature.fahrenheit
    low, high = _DENSITY[0], _DENSITY[-1]
    if degrees <= low[0]:
        return low[1]
    if degrees >= high[0]:
        return high[1]
    for earlier, later in zip(_DENSITY, _DENSITY[1:], strict=False):
        if earlier[0] <= degrees <= later[0]:
            span = later[0] - earlier[0]
            weight = (degrees - earlier[0]) / span
            return earlier[1] + (later[1] - earlier[1]) * weight
    return high[1]


def condensate_capacity(
    model: TrapModel,
    differential: Pressure,
    temperature: Temperature,
    *,
    discharge_coefficient: float = 0.61,
) -> MassFlow:
    """Condensate a trap orifice will pass at a given differential."""

    if differential.psia <= 0:
        raise ValidationError("a trap needs a differential to pass anything", field="differential")
    if not 0.0 < discharge_coefficient <= 1.0:
        raise ValidationError(
            "a discharge coefficient sits in (0, 1]", field="discharge_coefficient"
        )
    area = math.pi * (model.orifice_diameter_in / 2.0) ** 2
    density = condensate_density(temperature)
    pounds = (
        ORIFICE_CONSTANT * discharge_coefficient * area * math.sqrt(differential.psia * density)
    )
    return MassFlow.from_pounds_per_hour(pounds)


class SizingVerdict(Enum):
    UNDERSIZED = "undersized"
    CORRECT = "correct"
    OVERSIZED = "oversized"

    @property
    def label(self) -> str:
        return self.value

    @property
    def needs_attention(self) -> bool:
        return self is not SizingVerdict.CORRECT


@dataclass(frozen=True)
class SizingCheck:
    """A trap held against the load it is supposed to drain."""

    model: TrapModel
    load: MassFlow
    capacity: MassFlow
    safety_factor: float

    @property
    def required(self) -> MassFlow:
        return self.load.scaled(self.safety_factor)

    @property
    def ratio(self) -> float:
        """Capacity over the load, before the safety factor."""

        if self.load.is_zero:
            return float("inf")
        return self.capacity.pounds_per_hour / self.load.pounds_per_hour

    @property
    def verdict(self) -> SizingVerdict:
        if self.capacity.pounds_per_hour < self.required.pounds_per_hour:
            return SizingVerdict.UNDERSIZED
        if self.ratio > OVERSIZE_LIMIT:
            return SizingVerdict.OVERSIZED
        return SizingVerdict.CORRECT

    @property
    def note(self) -> str:
        if self.verdict is SizingVerdict.UNDERSIZED:
            return (
                f"passes {self.capacity} against a {self.required} requirement, "
                "so condensate backs up"
            )
        if self.verdict is SizingVerdict.OVERSIZED:
            return (
                f"passes {self.ratio:.1f} times the load, so it cycles on steam "
                "and cuts its own seat"
            )
        return f"passes {self.ratio:.1f} times the load, which is inside the band"

    def __str__(self) -> str:
        return f"{self.model.code} {self.verdict.label}: {self.note}"


def check_sizing(
    model: TrapModel,
    load: MassFlow,
    differential: Pressure,
    temperature: Temperature,
    *,
    safety_factor: float = DEFAULT_SAFETY_FACTOR,
) -> SizingCheck:
    """Hold a trap against a condensate load."""

    if safety_factor < 1.0:
        raise ValidationError("a safety factor is at least one", field="safety_factor")
    return SizingCheck(
        model=model,
        load=load,
        capacity=condensate_capacity(model, differential, temperature),
        safety_factor=safety_factor,
    )
