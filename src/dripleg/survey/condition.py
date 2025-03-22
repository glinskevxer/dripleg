"""The verdict a technician writes on the line for one trap.

Eleven codes, and the split that matters is not failed against not failed. It
is these three questions, which are independent of each other:

- is steam going past that should not be, which is the money
- is condensate being held back that should not be, which is the process risk
- was the trap actually assessed at all, which is the coverage number

A trap that was not found is not a pass and it is not a failure. Counting it as
either is how a survey ends up reporting ninety eight percent coverage on a
route where a fifth of the tags were never located.

The severity factor is the fraction of the seat that is passing steam, and it
is the number the loss engine multiplies Napier by. These are the survey
standard's defaults for a code entered without a measured leak size.
"""

from __future__ import annotations

from enum import Enum

from dripleg.errors import ValidationError

__all__ = ["TrapCondition"]


class TrapCondition(Enum):
    OK = "ok"
    LEAKING = "leaking"
    BLOWING_THROUGH = "blowing_through"
    RAPID_CYCLING = "rapid_cycling"
    FAILED_CLOSED = "failed_closed"
    PLUGGED = "plugged"
    FLOODED = "flooded"
    NO_LOAD = "no_load"
    OUT_OF_SERVICE = "out_of_service"
    NOT_FOUND = "not_found"
    INACCESSIBLE = "inaccessible"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")

    @property
    def was_assessed(self) -> bool:
        """Whether the technician actually got a reading on this trap."""

        return self not in {TrapCondition.NOT_FOUND, TrapCondition.INACCESSIBLE}

    @property
    def is_in_service(self) -> bool:
        """Whether the trap was live. An isolated trap loses nothing."""

        return self.was_assessed and self is not TrapCondition.OUT_OF_SERVICE

    @property
    def wastes_steam(self) -> bool:
        return self.severity_factor > 0.0

    @property
    def blocks_condensate(self) -> bool:
        """The failure that backs water up into the equipment."""

        return self in {TrapCondition.FAILED_CLOSED, TrapCondition.PLUGGED}

    @property
    def is_failure(self) -> bool:
        return self.wastes_steam or self.blocks_condensate

    @property
    def needs_repair(self) -> bool:
        """Whether this code puts the trap on the work list.

        A trap that could not be found goes on the list too. Somebody has to go
        back and either locate it or take it off the register, and leaving it
        off the list is how a tag stays lost for four survey cycles.
        """

        return self.is_failure or not self.was_assessed

    @property
    def severity_factor(self) -> float:
        """Fraction of the orifice passing live steam, on the code alone."""

        return {
            TrapCondition.OK: 0.0,
            TrapCondition.LEAKING: 0.25,
            TrapCondition.BLOWING_THROUGH: 1.0,
            TrapCondition.RAPID_CYCLING: 0.10,
            TrapCondition.FAILED_CLOSED: 0.0,
            TrapCondition.PLUGGED: 0.0,
            TrapCondition.FLOODED: 0.0,
            TrapCondition.NO_LOAD: 0.0,
            TrapCondition.OUT_OF_SERVICE: 0.0,
            TrapCondition.NOT_FOUND: 0.0,
            TrapCondition.INACCESSIBLE: 0.0,
        }[self]

    @property
    def rank(self) -> int:
        """Ordering for a report: worst first, unassessed last."""

        return {
            TrapCondition.BLOWING_THROUGH: 0,
            TrapCondition.FAILED_CLOSED: 1,
            TrapCondition.PLUGGED: 2,
            TrapCondition.LEAKING: 3,
            TrapCondition.RAPID_CYCLING: 4,
            TrapCondition.FLOODED: 5,
            TrapCondition.NO_LOAD: 6,
            TrapCondition.OK: 7,
            TrapCondition.OUT_OF_SERVICE: 8,
            TrapCondition.NOT_FOUND: 9,
            TrapCondition.INACCESSIBLE: 10,
        }[self]

    @classmethod
    def parse(cls, text: str) -> TrapCondition:
        cleaned = text.strip().lower().replace(" ", "_").replace("-", "_")
        for member in cls:
            if member.value == cleaned:
                return member
        alias = _ALIASES.get(cleaned)
        if alias is not None:
            return alias
        raise ValidationError(f"{text!r} is not a trap condition", field="condition")

    @classmethod
    def failures(cls) -> list[TrapCondition]:
        return sorted((c for c in cls if c.is_failure), key=lambda c: c.rank)

    @classmethod
    def in_report_order(cls) -> list[TrapCondition]:
        return sorted(cls, key=lambda c: c.rank)


# What the three field tablets in use here actually write into the column.
_ALIASES: dict[str, TrapCondition] = {
    "pass": TrapCondition.OK,
    "good": TrapCondition.OK,
    "blow_through": TrapCondition.BLOWING_THROUGH,
    "blowthrough": TrapCondition.BLOWING_THROUGH,
    "failed_open": TrapCondition.BLOWING_THROUGH,
    "open": TrapCondition.BLOWING_THROUGH,
    "cold": TrapCondition.FAILED_CLOSED,
    "closed": TrapCondition.FAILED_CLOSED,
    "blocked": TrapCondition.PLUGGED,
    "strainer": TrapCondition.PLUGGED,
    "cycling_fast": TrapCondition.RAPID_CYCLING,
    "waterlogged": TrapCondition.FLOODED,
    "isolated": TrapCondition.OUT_OF_SERVICE,
    "valved_off": TrapCondition.OUT_OF_SERVICE,
    "missing": TrapCondition.NOT_FOUND,
    "no_access": TrapCondition.INACCESSIBLE,
}
