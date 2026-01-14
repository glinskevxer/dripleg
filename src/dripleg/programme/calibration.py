"""How well the crew's own codes line up with the rules, technician by technician.

This is the report a contractor does not ask for and a plant should. A survey
is only as good as the person walking it, and the two ways it goes wrong are
opposite and need different remedies.

Over-calling is writing failure on traps the rules say are passing. It costs
money directly: every one of those becomes a work order, a trap and an hour of
labour on something that did not need it.

Under-calling is writing pass on traps the rules say are failing. It costs
more, quietly, because the loss runs for another whole survey cycle and the
report the plant acted on said everything was fine.

Both are per person, because they are training problems and training is per
person. The method mix is here too: a technician taking one reading where the
standard asks for two is not necessarily wrong, but every verdict they produce
is provisional and somebody should know that before the numbers are used.
"""

from __future__ import annotations

from dataclasses import dataclass

from dripleg.diagnosis.batch import SurveyDiagnosis
from dripleg.errors import ValidationError
from dripleg.survey.survey import Survey

__all__ = ["CalibrationReport", "TechnicianRecord", "calibrate"]

MIN_READINGS = 10
"""Below this many readings a technician's rates are not worth quoting."""


@dataclass(frozen=True)
class TechnicianRecord:
    """One person's readings on one survey, held against the rules."""

    technician: str
    read: int
    agreed: int
    over_called: int
    under_called: int
    not_reached: int
    two_method: int

    def __post_init__(self) -> None:
        if self.read < 0:
            raise ValidationError("a reading count is not negative", field="read")
        if self.agreed + self.over_called + self.under_called > self.read:
            raise ValidationError(
                f"{self.technician} has more outcomes than readings", field="agreed"
            )

    @property
    def agreement_rate(self) -> float:
        if self.read == 0:
            return 0.0
        return self.agreed / self.read

    @property
    def two_method_rate(self) -> float:
        if self.read == 0:
            return 0.0
        return self.two_method / self.read

    @property
    def not_reached_rate(self) -> float:
        if self.read == 0:
            return 0.0
        return self.not_reached / self.read

    @property
    def is_reportable(self) -> bool:
        return self.read >= MIN_READINGS

    @property
    def leans(self) -> str:
        """Which way this person's disagreements go."""

        if self.over_called == self.under_called:
            return "even"
        return "over" if self.over_called > self.under_called else "under"

    def __str__(self) -> str:
        if not self.is_reportable:
            return f"{self.technician}: {self.read} readings, too few to rate"
        return (
            f"{self.technician}: {self.agreement_rate:.0%} agreement over {self.read} "
            f"readings, leans {self.leans}"
        )


@dataclass(frozen=True)
class CalibrationReport:
    """Everybody who walked one survey."""

    reference: str
    records: list[TechnicianRecord]

    @property
    def technicians(self) -> int:
        return len(self.records)

    @property
    def read(self) -> int:
        return sum(record.read for record in self.records)

    def reportable(self) -> list[TechnicianRecord]:
        return [record for record in self.records if record.is_reportable]

    @property
    def worst_agreement(self) -> TechnicianRecord | None:
        rated = self.reportable()
        if not rated:
            return None
        return min(rated, key=lambda record: (record.agreement_rate, record.technician))

    def leaning(self, direction: str) -> list[TechnicianRecord]:
        if direction not in {"over", "under", "even"}:
            return []
        return [record for record in self.reportable() if record.leans == direction]

    @property
    def spread(self) -> float:
        """Gap between the best and worst agreement rates, where it can be told."""

        rated = self.reportable()
        if len(rated) < 2:
            return 0.0
        rates = [record.agreement_rate for record in rated]
        return max(rates) - min(rates)

    def __str__(self) -> str:
        return f"{self.reference}: {self.technicians} technicians, {self.read} readings"


def calibrate(survey: Survey, diagnosis: SurveyDiagnosis) -> CalibrationReport:
    """Line every reading up against the verdict the rules produced for it."""

    by_person: dict[str, dict[str, int]] = {}
    for observation in survey.observations:
        result = diagnosis.find(observation.tag)
        if result is None:
            continue
        counts = by_person.setdefault(
            observation.technician,
            {
                "read": 0,
                "agreed": 0,
                "over": 0,
                "under": 0,
                "not_reached": 0,
                "two_method": 0,
            },
        )
        counts["read"] += 1
        if observation.is_two_method:
            counts["two_method"] += 1
        if not observation.reported_condition.was_assessed:
            counts["not_reached"] += 1
        if result.agrees_with_technician:
            counts["agreed"] += 1
        elif observation.reported_condition.is_failure and not result.condition.is_failure:
            counts["over"] += 1
        elif not observation.reported_condition.is_failure and result.condition.is_failure:
            counts["under"] += 1
    return CalibrationReport(
        reference=diagnosis.reference,
        records=sorted(
            (
                TechnicianRecord(
                    technician=name,
                    read=counts["read"],
                    agreed=counts["agreed"],
                    over_called=counts["over"],
                    under_called=counts["under"],
                    not_reached=counts["not_reached"],
                    two_method=counts["two_method"],
                )
                for name, counts in by_person.items()
            ),
            key=lambda record: (record.agreement_rate, record.technician),
        ),
    )
