"""How much steam goes through a hole, which is the whole loss calculation.

Napier's formula for saturated steam through a sharp edged orifice, in the
form the trade uses:

    W = 51.43 x Cd x A x P

with W in pounds per hour, A the orifice area in square inches and P the
absolute upstream pressure in psia. It is a straight line in pressure, which
looks too simple until you remember it only holds while the flow is choked, and
a trap seat discharging to a return line almost always is.

Two things get added to it here and neither is optional in the field.

The discharge coefficient is not one. A drilled orifice passes about 0.61 of
the ideal, a worn trap seat rather more because it is no longer sharp edged, and
a survey that leaves Cd out overstates every loss by a third and gets the whole
report dismissed.

Back pressure matters once the ratio climbs past the critical one. Below that
the seat is choked and downstream pressure does nothing at all. Above it the
flow falls away, and the approximation used here is the elliptical one from
valve sizing: exact enough for a survey, and stated plainly rather than hidden.
"""

from __future__ import annotations

import math

from dripleg.errors import ValidationError
from dripleg.thresholds import CRITICAL_BACK_PRESSURE_RATIO
from dripleg.units.flow import MassFlow
from dripleg.units.pressure import Pressure

__all__ = [
    "CRITICAL_PRESSURE_RATIO",
    "NAPIER_CONSTANT",
    "SHARP_ORIFICE_CD",
    "WORN_SEAT_CD",
    "back_pressure_factor",
    "orifice_area",
    "orifice_flow",
]

NAPIER_CONSTANT = 51.43
"""Pounds an hour per square inch of orifice per psia, saturated steam."""

CRITICAL_PRESSURE_RATIO = CRITICAL_BACK_PRESSURE_RATIO
"""Kept under this name because the loss code reads better with it."""

SHARP_ORIFICE_CD = 0.61
"""A drilled, square edged hole: a fixed orifice trap or a new seat."""

WORN_SEAT_CD = 0.75
"""A seat that has been cut by wire drawing, so no longer square edged."""

MIN_ORIFICE_IN = 0.001
MAX_ORIFICE_IN = 2.0


def orifice_area(diameter_in: float) -> float:
    """Area of a round orifice in square inches."""

    if not MIN_ORIFICE_IN <= diameter_in <= MAX_ORIFICE_IN:
        raise ValidationError(
            f"{diameter_in:g} inch is not a trap orifice diameter",
            field="diameter_in",
        )
    return math.pi * (diameter_in / 2.0) ** 2


def back_pressure_factor(upstream: Pressure, downstream: Pressure) -> float:
    """How much of the choked flow survives the back pressure.

    One while the seat is choked, falling to zero as the two pressures meet.
    The curve between is an ellipse, which is the approximation control valve
    sizing has used for decades and is well inside the error of guessing the
    orifice size in the first place.
    """

    if downstream.psia > upstream.psia:
        raise ValidationError(
            "back pressure cannot be above the steam pressure",
            field="downstream",
        )
    if upstream.psia <= 0:
        raise ValidationError("there is no flow from no pressure", field="upstream")
    ratio = downstream.psia / upstream.psia
    if ratio <= CRITICAL_PRESSURE_RATIO:
        return 1.0
    span = (ratio - CRITICAL_PRESSURE_RATIO) / (1.0 - CRITICAL_PRESSURE_RATIO)
    return math.sqrt(max(1.0 - span * span, 0.0))


def orifice_flow(
    upstream: Pressure,
    diameter_in: float,
    *,
    downstream: Pressure | None = None,
    discharge_coefficient: float = SHARP_ORIFICE_CD,
    open_fraction: float = 1.0,
) -> MassFlow:
    """Saturated steam through an orifice, in pounds an hour.

    `open_fraction` is how much of the seat is passing, which is where the
    survey condition code comes in: a trap blowing through is passing all of
    it, one leaking past a damaged seat rather less.
    """

    if not 0.0 < discharge_coefficient <= 1.0:
        raise ValidationError(
            f"a discharge coefficient sits in (0, 1], got {discharge_coefficient:g}",
            field="discharge_coefficient",
        )
    if not 0.0 <= open_fraction <= 1.0:
        raise ValidationError(
            f"the open fraction of a seat sits in [0, 1], got {open_fraction:g}",
            field="open_fraction",
        )
    if open_fraction == 0.0:
        return MassFlow.zero()
    area = orifice_area(diameter_in) * open_fraction
    choked = NAPIER_CONSTANT * discharge_coefficient * area * upstream.psia
    if downstream is None:
        return MassFlow.from_pounds_per_hour(choked)
    return MassFlow.from_pounds_per_hour(choked * back_pressure_factor(upstream, downstream))
