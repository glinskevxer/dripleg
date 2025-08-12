"""Which traps keep failing, and whether it is the trap or where it is.

The question a plant asks after three surveys is not how many failed. It is
whether the failures are spread evenly, and they never are. Failures cluster by
model, by principle, by pressure class and by station, and each cluster points
somewhere different:

- one model failing everywhere is a purchasing decision
- one principle failing on one pressure class is an application decision
- one station failing whatever is fitted to it is a piping problem, usually a
  trap sized for a load that is not there, and changing the trap again will not
  fix it

The last one is the useful one and the one nobody reports, because it needs the
history keyed by station rather than by trap.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from dripleg.errors import ValidationError
from dripleg.model.attributes import ServiceType
from dripleg.model.header import PressureClass
from dripleg.model.principles import OperatingPrinciple
from dripleg.model.register import TrapRegister
from dripleg.model.tags import TrapTag
from dripleg.survey.condition import TrapCondition

__all__ = ["FailureRate", "ReliabilityReport", "build_reliability"]

MIN_SAMPLE = 5
"""Below this many readings a failure rate is noise and is reported as such."""


@dataclass(frozen=True)
class FailureRate:
    """Failures over assessments for one slice of the population."""

    label: str
    assessed: int
    failed: int

    def __post_init__(self) -> None:
        if self.assessed < 0 or self.failed < 0:
            raise ValidationError("a count is not negative", field="assessed")
        if self.failed > self.assessed:
            raise ValidationError(
                f"{self.label} has more failures than assessments", field="failed"
            )

    @property
    def rate(self) -> float:
        if self.assessed == 0:
            return 0.0
        return self.failed / self.assessed

    @property
    def is_reportable(self) -> bool:
        return self.assessed >= MIN_SAMPLE

    def __str__(self) -> str:
        if not self.is_reportable:
            return f"{self.label}: {self.failed} of {self.assessed}, too few to rate"
        return f"{self.label}: {self.failed} of {self.assessed} ({self.rate:.0%})"


@dataclass(frozen=True)
class Reading:
    """One historical verdict, flattened to what reliability needs."""

    tag: TrapTag
    condition: TrapCondition


def _rate(label: str, readings: Iterable[Reading]) -> FailureRate:
    assessed = 0
    failed = 0
    for reading in readings:
        if not reading.condition.was_assessed:
            continue
        assessed += 1
        if reading.condition.is_failure:
            failed += 1
    return FailureRate(label=label, assessed=assessed, failed=failed)


class ReliabilityReport:
    """Failure rates cut four ways, plus the stations that keep coming back."""

    def __init__(
        self,
        by_model: list[FailureRate],
        by_principle: list[FailureRate],
        by_service: list[FailureRate],
        by_pressure: list[FailureRate],
        repeat_offenders: list[tuple[TrapTag, int]],
    ) -> None:
        self.by_model = sorted(by_model, key=lambda r: (-r.rate, r.label))
        self.by_principle = sorted(by_principle, key=lambda r: (-r.rate, r.label))
        self.by_service = sorted(by_service, key=lambda r: (-r.rate, r.label))
        self.by_pressure = sorted(by_pressure, key=lambda r: (-r.rate, r.label))
        self.repeat_offenders = repeat_offenders

    @property
    def worst_model(self) -> FailureRate | None:
        reportable = [r for r in self.by_model if r.is_reportable]
        return reportable[0] if reportable else None

    @property
    def worst_principle(self) -> FailureRate | None:
        reportable = [r for r in self.by_principle if r.is_reportable]
        return reportable[0] if reportable else None

    def stations_failing_at_least(self, times: int) -> list[TrapTag]:
        if times < 1:
            raise ValidationError("a repeat offender fails at least once", field="times")
        return [tag for tag, count in self.repeat_offenders if count >= times]

    @property
    def has_a_purchasing_problem(self) -> bool:
        """One model failing far worse than the rest, on a real sample."""

        reportable = [r for r in self.by_model if r.is_reportable]
        if len(reportable) < 2:
            return False
        return reportable[0].rate >= 2 * reportable[-1].rate and reportable[0].rate >= 0.25

    def __str__(self) -> str:
        return (
            f"{len(self.by_model)} models, {len(self.repeat_offenders)} stations "
            "failing more than once"
        )


def build_reliability(
    register: TrapRegister,
    history: dict[TrapTag, list[TrapCondition]],
) -> ReliabilityReport:
    """Cut the survey history by what was fitted and where."""

    by_model: dict[str, list[Reading]] = {}
    by_principle: dict[OperatingPrinciple, list[Reading]] = {}
    by_service: dict[ServiceType, list[Reading]] = {}
    by_pressure: dict[PressureClass, list[Reading]] = {}
    failures: Counter[TrapTag] = Counter()
    for station in register:
        verdicts = history.get(station.tag, [])
        readings = [Reading(tag=station.tag, condition=condition) for condition in verdicts]
        if not readings:
            continue
        model_key = f"{station.model.manufacturer} {station.model.code}"
        by_model.setdefault(model_key, []).extend(readings)
        by_principle.setdefault(station.model.principle, []).extend(readings)
        by_service.setdefault(station.service, []).extend(readings)
        by_pressure.setdefault(station.header.pressure_class, []).extend(readings)
        failures[station.tag] = sum(1 for r in readings if r.condition.is_failure)
    return ReliabilityReport(
        by_model=[_rate(name, readings) for name, readings in by_model.items()],
        by_principle=[
            _rate(principle.label, readings) for principle, readings in by_principle.items()
        ],
        by_service=[_rate(service.label, readings) for service, readings in by_service.items()],
        by_pressure=[_rate(pressure.label, readings) for pressure, readings in by_pressure.items()],
        repeat_offenders=sorted(
            ((tag, count) for tag, count in failures.items() if count > 1),
            key=lambda pair: (-pair[1], str(pair[0])),
        ),
    )
