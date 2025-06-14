"""Running the engine over a whole survey, and what falls out that is not a verdict.

Two things a per trap diagnosis cannot tell you and this can.

The first is the disagreement rate between the field codes and the rules. A
crew that agrees with the rules ninety five percent of the time is calibrated.
One that agrees sixty percent of the time is either working to a different
standard or guessing, and either way the survey needs a conversation before it
needs a repair list.

The second is the readings that could not be diagnosed at all: tags that are
not on the register, and traps that were pulled before the survey walked past
them. Those are register maintenance, not trap failures, and mixing them into
the failure count is how a plant ends up chasing traps that do not exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dripleg.diagnosis.context import DiagnosisContext
from dripleg.diagnosis.engine import Diagnosis, DiagnosisEngine
from dripleg.model.register import TrapRegister
from dripleg.model.tags import TrapTag
from dripleg.survey.condition import TrapCondition
from dripleg.survey.survey import Survey

__all__ = ["SurveyDiagnosis", "diagnose_survey"]


@dataclass(frozen=True)
class SurveyDiagnosis:
    """Every verdict from one survey, plus what could not be judged."""

    reference: str
    results: list[Diagnosis]
    unregistered: list[TrapTag] = field(default_factory=list)
    out_of_service_on_the_day: list[TrapTag] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.results)

    @property
    def skipped(self) -> list[TrapTag]:
        return sorted([*self.unregistered, *self.out_of_service_on_the_day])

    def condition_counts(self) -> dict[TrapCondition, int]:
        counts: dict[TrapCondition, int] = {}
        for result in self.results:
            counts[result.condition] = counts.get(result.condition, 0) + 1
        return dict(sorted(counts.items(), key=lambda pair: pair[0].rank))

    def failures(self) -> list[Diagnosis]:
        return [r for r in self.results if r.condition.is_failure]

    def wasting_steam(self) -> list[Diagnosis]:
        return [r for r in self.results if r.condition.wastes_steam]

    def provisional(self) -> list[Diagnosis]:
        return [r for r in self.results if r.is_provisional]

    def disagreements(self) -> list[Diagnosis]:
        return [r for r in self.results if not r.agrees_with_technician]

    @property
    def agreement_rate(self) -> float:
        if not self.results:
            return 0.0
        agreed = sum(1 for r in self.results if r.agrees_with_technician)
        return agreed / len(self.results)

    @property
    def failure_rate(self) -> float:
        judged = [r for r in self.results if r.condition.was_assessed]
        if not judged:
            return 0.0
        return len([r for r in judged if r.condition.is_failure]) / len(judged)

    def find(self, tag: TrapTag | str) -> Diagnosis | None:
        wanted = tag if isinstance(tag, TrapTag) else TrapTag.parse(tag)
        for result in self.results:
            if result.tag == wanted:
                return result
        return None

    def worst_first(self) -> list[Diagnosis]:
        return sorted(self.results, key=lambda r: (r.condition.rank, -r.confidence, r.tag))

    def __str__(self) -> str:
        return (
            f"{self.reference}: {len(self.results)} judged, "
            f"{len(self.failures())} failures, {len(self.skipped)} skipped"
        )


def diagnose_survey(
    register: TrapRegister,
    survey: Survey,
    engine: DiagnosisEngine | None = None,
) -> SurveyDiagnosis:
    """Judge every reading on a survey that can be judged."""

    running = engine if engine is not None else DiagnosisEngine()
    results: list[Diagnosis] = []
    unregistered: list[TrapTag] = []
    retired: list[TrapTag] = []
    for observation in survey.observations:
        station = register.find(observation.tag)
        if station is None:
            unregistered.append(observation.tag)
            continue
        if not station.is_in_service_on(observation.observed_on):
            retired.append(observation.tag)
            continue
        results.append(running.diagnose(DiagnosisContext(station, observation)))
    return SurveyDiagnosis(
        reference=survey.reference,
        results=results,
        unregistered=unregistered,
        out_of_service_on_the_day=retired,
    )
