"""Every number this package compares a reading against, in one file.

It sits at the top of the package rather than under the rules because the model
layer needs one of them too, and a model module reaching into the diagnosis
layer to find a constant is the wrong way round.

These started out as private constants at the top of whichever rule module
first needed them, and two of them ended up defined twice with the same value,
which is the state a number is in immediately before somebody changes one copy.

Having them together is worth more than tidiness. A site's survey standard is
these eleven numbers, and an engineer arguing with a verdict wants to read them
as a set rather than find them one at a time in the rules. Each one carries why
it is what it is, because a threshold with no reason on it gets moved by the
next person to disagree with a single reading.
"""

from __future__ import annotations

__all__ = [
    "AMBIENT_MARGIN_F",
    "COLD_INLET_F",
    "CRITICAL_BACK_PRESSURE_RATIO",
    "OUTLET_MARGIN_F",
    "PRESSURE_DISAGREEMENT",
    "SUBCOOLED_FLOOR_F",
]

CRITICAL_BACK_PRESSURE_RATIO = 0.577
"""Downstream over upstream absolute, below which a seat is choked.

Saturated steam, k around 1.135. Above this the loss calculation stops being a
straight line in pressure and the diagnosis has to say so.
"""

OUTLET_MARGIN_F = 12.0
"""How close to discharge line saturation counts as steam downstream.

A contact probe on a pipe reads under the fluid inside it, and twelve degrees
is what that costs on lagged pipe with a decent probe.
"""

COLD_INLET_F = 100.0
"""Degrees under saturation at which the inlet says nothing is getting through.

Well past what any thermostatic trap subcools by, so a reading this far down is
a trap holding condensate rather than a trap working as designed.
"""

AMBIENT_MARGIN_F = 35.0
"""How close to the air a pipe has to read before the line is called dead.

Wide enough that a poorly lagged line on a cold morning does not read as
isolated, narrow enough that a live main never does.
"""

SUBCOOLED_FLOOR_F = 0.0
"""Below this the inlet is above saturation, which is superheat, not subcooling.

Superheat on a drip leg is not a fault and is not something the subcooling
rules have anything to say about.
"""

PRESSURE_DISAGREEMENT = 0.20
"""How far a measured header pressure may sit off the register before it is flagged.

A fifth. Beyond that either the register is stale or the gauge is wrong, and
both are worth saying before anything is concluded from the number.
"""
