"""The survey report: what was looked at, what was found, what was not reached.

Order matters here and it is not the obvious one. Coverage comes first, before
any finding, because every number under it is conditional on it. A report that
opens with a failure rate and buries the fact that a fifth of the route was
never located has told the reader the wrong thing first.

The disagreement block is the one nobody asks for and everybody uses. It lists
the traps where the field code and the rules parted company, which is where the
next survey's training goes.
"""

from __future__ import annotations

from dataclasses import dataclass

from dripleg.diagnosis.batch import SurveyDiagnosis
from dripleg.model.register import TrapRegister
from dripleg.report.base import Rendered
from dripleg.report.table import Column, Table
from dripleg.survey.survey import Survey

__all__ = ["SurveyReport", "build_survey_report"]


@dataclass(frozen=True)
class SurveyReport(Rendered):
    """One survey, rendered."""

    reference: str
    name: str
    contractor: str
    started_on: str
    finished_on: str
    on_register: int
    observed: int
    assessed: int
    not_found: int
    inaccessible: int
    condition_counts: dict[str, int]
    failure_rate: float
    agreement_rate: float
    disagreements: list[tuple[str, str, str]]
    skipped: list[str]

    @property
    def coverage(self) -> float:
        if self.on_register == 0:
            return 0.0
        return self.assessed / self.on_register

    @property
    def headline(self) -> str:
        return (
            f"{self.reference} {self.name}: {self.assessed} of {self.on_register} assessed, "
            f"{self.failure_rate:.0%} of those failed"
        )

    def summary_lines(self) -> list[str]:
        return [
            f"survey        {self.reference}  {self.name}",
            f"contractor    {self.contractor}",
            f"dates         {self.started_on} to {self.finished_on}",
            f"on register   {self.on_register}",
            f"assessed      {self.assessed} ({self.coverage:.1%})",
            f"not found     {self.not_found}",
            f"inaccessible  {self.inaccessible}",
            f"failure rate  {self.failure_rate:.1%} of what was assessed",
            f"agreement     {self.agreement_rate:.1%} with the field codes",
        ]

    def condition_table(self) -> Table:
        table = Table([Column("condition"), Column.number("traps"), Column.number("share")])
        total = sum(self.condition_counts.values())
        for label, count in self.condition_counts.items():
            share = f"{count / total:.1%}" if total else "0.0%"
            table.add([label, count, share])
        return table

    def disagreement_table(self) -> Table:
        table = Table([Column("tag"), Column("field code"), Column("rules said")])
        table.extend(self.disagreements)
        return table

    def lines(self) -> list[str]:
        out = [self.headline, ""]
        out.extend(self.summary_lines())
        out.extend(["", "conditions", ""])
        out.extend(self.condition_table().lines())
        if self.disagreements:
            out.extend(["", "where the rules and the field code parted company", ""])
            out.extend(self.disagreement_table().lines())
        if self.skipped:
            out.extend(["", "readings that could not be judged", ""])
            out.extend(f"  {tag}" for tag in self.skipped)
        return out

    def as_dict(self) -> dict[str, object]:
        return {
            "reference": self.reference,
            "name": self.name,
            "contractor": self.contractor,
            "started_on": self.started_on,
            "finished_on": self.finished_on,
            "on_register": self.on_register,
            "observed": self.observed,
            "assessed": self.assessed,
            "not_found": self.not_found,
            "inaccessible": self.inaccessible,
            "coverage": round(self.coverage, 4),
            "failure_rate": round(self.failure_rate, 4),
            "agreement_rate": round(self.agreement_rate, 4),
            "conditions": dict(self.condition_counts),
            "disagreements": [
                {"tag": tag, "field": field, "rules": rules}
                for tag, field, rules in self.disagreements
            ],
            "skipped": list(self.skipped),
        }


def build_survey_report(
    register: TrapRegister,
    survey: Survey,
    diagnosis: SurveyDiagnosis,
) -> SurveyReport:
    coverage = survey.coverage(register)
    return SurveyReport(
        reference=survey.reference,
        name=survey.name,
        contractor=survey.contractor,
        started_on=survey.started_on.isoformat(),
        finished_on=(survey.finished_on.isoformat() if survey.finished_on is not None else "open"),
        on_register=coverage.on_register,
        observed=coverage.observed,
        assessed=coverage.assessed,
        not_found=coverage.not_found,
        inaccessible=coverage.inaccessible,
        condition_counts={
            condition.label: count for condition, count in diagnosis.condition_counts().items()
        },
        failure_rate=diagnosis.failure_rate,
        agreement_rate=diagnosis.agreement_rate,
        disagreements=[
            (str(result.tag), result.reported_condition.label, result.condition.label)
            for result in diagnosis.disagreements()
        ],
        skipped=[str(tag) for tag in diagnosis.skipped],
    )
