"""How each kind of steam trap works, because that is what a reading means.

A survey reading on its own says almost nothing. Forty decibels of ultrasound
is a healthy inverted bucket cycling and a failed thermodynamic disc, and a
steady 250 F downstream is normal on a float and thermostatic and a plugged
strainer on a disc. The diagnosis engine later on is mostly the business of
holding a reading up against what the principle is supposed to sound and feel
like, so the expectations live here as data rather than in the rules.

The numbers are the ones the survey standard here works to. They are field
heuristics rather than physics, which is why they are collected in one place
with their reasons written down and not spread through the rule bodies.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from dripleg.errors import ValidationError

__all__ = ["DischargePattern", "FailureTendency", "OperatingPrinciple", "PrincipleProfile"]


class DischargePattern(Enum):
    """What a healthy trap of this kind does when you stand next to it."""

    INTERMITTENT = "intermittent"
    CYCLIC = "cyclic"
    CONTINUOUS = "continuous"
    MODULATING = "modulating"

    @property
    def is_audible_cycling(self) -> bool:
        return self in {DischargePattern.INTERMITTENT, DischargePattern.CYCLIC}


class FailureTendency(Enum):
    """Which way this kind of trap usually fails, which sets the search order."""

    OPEN = "open"
    CLOSED = "closed"
    EITHER = "either"


class OperatingPrinciple(Enum):
    THERMODYNAMIC_DISC = "thermodynamic_disc"
    INVERTED_BUCKET = "inverted_bucket"
    FLOAT_THERMOSTATIC = "float_thermostatic"
    BALANCED_PRESSURE = "balanced_pressure"
    BIMETALLIC = "bimetallic"
    FIXED_ORIFICE = "fixed_orifice"
    VENTURI = "venturi"

    @property
    def profile(self) -> PrincipleProfile:
        return PRINCIPLES[self]

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")


@dataclass(frozen=True)
class PrincipleProfile:
    """What to expect from a healthy trap of one kind."""

    principle: OperatingPrinciple
    pattern: DischargePattern
    tendency: FailureTendency
    cycles_per_minute: tuple[float, float]
    subcooling_f: tuple[float, float]
    holds_condensate_back: bool
    sound_carries_upstream: bool
    note: str

    def __post_init__(self) -> None:
        low, high = self.cycles_per_minute
        if low < 0 or high < low:
            raise ValidationError("a cycle rate band runs low to high", field="cycles_per_minute")
        cool_low, cool_high = self.subcooling_f
        if cool_low < 0 or cool_high < cool_low:
            raise ValidationError("a subcooling band runs low to high", field="subcooling_f")
        if not self.note.strip():
            raise ValidationError("say why the numbers are what they are", field="note")

    def cycle_rate_is_normal(self, per_minute: float) -> bool:
        low, high = self.cycles_per_minute
        if not self.pattern.is_audible_cycling:
            return per_minute <= high
        return low <= per_minute <= high

    def subcooling_is_normal(self, degrees_below_saturation: float) -> bool:
        low, high = self.subcooling_f
        return low <= degrees_below_saturation <= high

    @property
    def discharges_at_saturation(self) -> bool:
        """A trap that lets condensate go the moment it forms."""

        return self.subcooling_f[1] <= 10.0


PRINCIPLES: dict[OperatingPrinciple, PrincipleProfile] = {
    OperatingPrinciple.THERMODYNAMIC_DISC: PrincipleProfile(
        principle=OperatingPrinciple.THERMODYNAMIC_DISC,
        pattern=DischargePattern.INTERMITTENT,
        tendency=FailureTendency.OPEN,
        cycles_per_minute=(0.5, 8.0),
        subcooling_f=(0.0, 10.0),
        holds_condensate_back=False,
        sound_carries_upstream=True,
        note="the disc snaps shut on flash velocity, so a fast cycle is a worn seat",
    ),
    OperatingPrinciple.INVERTED_BUCKET: PrincipleProfile(
        principle=OperatingPrinciple.INVERTED_BUCKET,
        pattern=DischargePattern.INTERMITTENT,
        tendency=FailureTendency.OPEN,
        cycles_per_minute=(0.2, 6.0),
        subcooling_f=(0.0, 15.0),
        holds_condensate_back=True,
        sound_carries_upstream=True,
        note="loses its prime on a sudden pressure drop and then blows through",
    ),
    OperatingPrinciple.FLOAT_THERMOSTATIC: PrincipleProfile(
        principle=OperatingPrinciple.FLOAT_THERMOSTATIC,
        pattern=DischargePattern.CONTINUOUS,
        tendency=FailureTendency.CLOSED,
        cycles_per_minute=(0.0, 0.5),
        subcooling_f=(0.0, 10.0),
        holds_condensate_back=False,
        sound_carries_upstream=False,
        note="modulates against the load, so no cycling and a quiet steady flow",
    ),
    OperatingPrinciple.BALANCED_PRESSURE: PrincipleProfile(
        principle=OperatingPrinciple.BALANCED_PRESSURE,
        pattern=DischargePattern.CYCLIC,
        tendency=FailureTendency.EITHER,
        cycles_per_minute=(0.1, 3.0),
        subcooling_f=(10.0, 40.0),
        holds_condensate_back=True,
        sound_carries_upstream=False,
        note="waits for the condensate to cool, so a cold body is normal not failed",
    ),
    OperatingPrinciple.BIMETALLIC: PrincipleProfile(
        principle=OperatingPrinciple.BIMETALLIC,
        pattern=DischargePattern.CYCLIC,
        tendency=FailureTendency.CLOSED,
        cycles_per_minute=(0.1, 2.0),
        subcooling_f=(20.0, 90.0),
        holds_condensate_back=True,
        sound_carries_upstream=False,
        note="backs the condensate up a long way, which is the point on a tracer",
    ),
    OperatingPrinciple.FIXED_ORIFICE: PrincipleProfile(
        principle=OperatingPrinciple.FIXED_ORIFICE,
        pattern=DischargePattern.CONTINUOUS,
        tendency=FailureTendency.OPEN,
        cycles_per_minute=(0.0, 0.2),
        subcooling_f=(0.0, 5.0),
        holds_condensate_back=False,
        sound_carries_upstream=False,
        note="passes steam whenever the load drops below what the hole passes",
    ),
    OperatingPrinciple.VENTURI: PrincipleProfile(
        principle=OperatingPrinciple.VENTURI,
        pattern=DischargePattern.CONTINUOUS,
        tendency=FailureTendency.OPEN,
        cycles_per_minute=(0.0, 0.2),
        subcooling_f=(0.0, 8.0),
        holds_condensate_back=False,
        sound_carries_upstream=False,
        note="same as a fixed orifice with a longer throat and a better sales pitch",
    ),
}
