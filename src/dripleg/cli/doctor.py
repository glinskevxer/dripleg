"""`dripleg doctor`: everything that is wrong with a book, in one command.

The individual checks all exist already and nobody runs them, because running
six commands to find out whether a book is healthy is five commands more than
anybody does. So this runs the lot and prints one list, worst first, with an
exit code that says whether anything needs doing.

The exit code matters more than the output. A site running this from cron wants
a non zero exit when something has gone wrong, and wants silence otherwise.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import click

from dripleg.cli.context import Context
from dripleg.cli.loading import register_for
from dripleg.cli.output import emit_rows
from dripleg.errors import ConflictError
from dripleg.report.table import Column
from dripleg.store.audit import audit_book
from dripleg.store.migrations import MIGRATIONS, schema_version
from dripleg.store.risk_repo import RiskRepository
from dripleg.store.rules_repo import RulesRepository
from dripleg.store.survey_repo import RouteRepository
from dripleg.survey.route import unrouted_tags

__all__ = ["Complaint", "doctor_command", "examine"]

SEVERITIES = ("error", "warning", "note")


@dataclass(frozen=True)
class Complaint:
    """One thing the doctor found."""

    severity: str
    check: str
    detail: str

    @property
    def rank(self) -> int:
        return SEVERITIES.index(self.severity)

    @property
    def is_error(self) -> bool:
        return self.severity == "error"

    def __str__(self) -> str:
        return f"{self.severity}: {self.check}: {self.detail}"


def examine(context: Context, on: dt.date) -> list[Complaint]:
    """Run every check this build has against one site's book."""

    found: list[Complaint] = []
    try:
        context.book.integrity_check()
    except ConflictError as problem:
        found.append(Complaint("error", "integrity", str(problem)))
    version = schema_version(context.book)
    if version != MIGRATIONS[-1].number:
        found.append(
            Complaint(
                "error",
                "schema",
                f"the book is at version {version} and this build is at "
                f"{MIGRATIONS[-1].number}, run dripleg init",
            )
        )
    site = context.site()
    for finding in audit_book(context.book, site).findings:
        found.append(Complaint("error", finding.kind, finding.detail))
    for exclusion in RulesRepository(context.book).stale_exclusions(site):
        found.append(
            Complaint(
                "warning",
                "stale rule exclusion",
                f"{exclusion.rule_code} is switched off and this build does not have it",
            )
        )
    for risk in RiskRepository(context.book).due_for_review(site, on):
        found.append(
            Complaint(
                "warning",
                "accepted risk due for review",
                f"{risk.tag} was accepted by {risk.accepted_by} and was due back "
                f"on {risk.review_on}",
            )
        )
    register = register_for(context)
    routes = RouteRepository(context.book).list_for(site)
    if routes:
        missed = unrouted_tags(register, routes)
        if missed:
            found.append(
                Complaint(
                    "note",
                    "traps on no route",
                    f"{len(missed)} stations are on the register and on no route",
                )
            )
    elif len(register):
        found.append(Complaint("note", "no routes", "this site has stations and no routes at all"))
    return sorted(found, key=lambda complaint: (complaint.rank, complaint.check))


@click.command("doctor")
@click.option("--on", default=None, help="The day to judge review dates against.")
@click.option("--strict", is_flag=True, help="Fail on a warning as well as an error.")
@click.pass_obj
def doctor_command(context: Context, on: str | None, strict: bool) -> None:
    """Run every check on this book and say whether anything needs doing."""

    day = dt.date.fromisoformat(on) if on is not None else dt.date.today()
    complaints = examine(context, day)
    emit_rows(
        context,
        [Column("severity"), Column("check"), Column("detail", max_width=64)],
        [(c.severity, c.check, c.detail) for c in complaints],
        keys=["severity", "check", "detail"],
        empty="nothing wrong with this book",
    )
    worst = [c for c in complaints if c.is_error or (strict and c.severity == "warning")]
    if worst:
        raise SystemExit(1)
