"""`dripleg programme`: due dates, overdue traps and the reliability cuts."""

from __future__ import annotations

import datetime as dt

import click

from dripleg.cli.context import Context
from dripleg.cli.loading import diagnosis_for, loss_register_for, register_for
from dripleg.cli.output import emit_lines, emit_rows
from dripleg.loss.accrual import accrue_all
from dripleg.programme.reliability import build_reliability
from dripleg.programme.schedule import build_schedule
from dripleg.programme.trend import compare_surveys
from dripleg.report.programme_report import build_programme_report
from dripleg.report.scorecard import build_scorecard
from dripleg.report.table import Column
from dripleg.report.trend_report import build_trend_report
from dripleg.store.finding_repo import FindingRepository, WorkOrderRepository
from dripleg.store.survey_repo import SurveyRepository
from dripleg.units.money import Money

__all__ = ["programme_group"]


@click.group("programme")
def programme_group() -> None:
    """The survey programme: what is due and what keeps failing."""


def _day(text: str | None) -> dt.date:
    return dt.date.fromisoformat(text) if text is not None else dt.date.today()


@programme_group.command("due")
@click.option("--on", default=None, help="The day to work it out as at.")
@click.pass_obj
def programme_due(context: Context, on: str | None) -> None:
    """Compliance, the overdue register and next year's workload."""

    day = _day(on)
    register = register_for(context)
    history = FindingRepository(context.book).last_verdict_per_trap(context.site())
    schedule = build_schedule(register, history, on=day)
    report = build_programme_report(context.site(), schedule, day)
    emit_lines(context, report.lines(), report.as_dict())


@programme_group.command("overdue")
@click.option("--on", default=None, help="The day to work it out as at.")
@click.pass_obj
def programme_overdue(context: Context, on: str | None) -> None:
    """Only the traps that are late."""

    day = _day(on)
    register = register_for(context)
    history = FindingRepository(context.book).last_verdict_per_trap(context.site())
    schedule = build_schedule(register, history, on=day)
    emit_rows(
        context,
        [Column("tag"), Column("last seen"), Column("due"), Column.number("days late")],
        [
            (
                str(entry.tag),
                entry.last_surveyed.isoformat() if entry.last_surveyed else "never",
                entry.due_on.isoformat() if entry.due_on else "",
                entry.days_late_on(day),
            )
            for entry in schedule.overdue_on(day)
        ],
        keys=["tag", "last_seen", "due", "days_late"],
        empty="nothing overdue",
    )


@programme_group.command("compare")
@click.argument("earlier")
@click.argument("later")
@click.pass_obj
def programme_compare(context: Context, earlier: str, later: str) -> None:
    """Hold two saved surveys against each other, trap by trap."""

    repo = FindingRepository(context.book)
    trend = compare_surveys(
        repo.for_survey(context.site(), earlier),
        repo.for_survey(context.site(), later),
    )
    report = build_trend_report(trend)
    emit_lines(context, report.lines(), report.as_dict())


@programme_group.command("scorecard")
@click.argument("reference")
@click.option("--on", default=None, help="The day to work the programme out as at.")
@click.pass_obj
def programme_scorecard(context: Context, reference: str, on: str | None) -> None:
    """The whole programme on one page."""

    day = _day(on)
    register = register_for(context)
    survey = SurveyRepository(context.book).get(context.site(), reference)
    diagnosis = diagnosis_for(context, reference)
    losses = loss_register_for(context, reference)
    findings = FindingRepository(context.book)
    schedule = build_schedule(register, findings.last_verdict_per_trap(context.site()), on=day)
    orders = WorkOrderRepository(context.book)
    states = orders.count_by_state(context.site())
    raised = sum(states.values())
    verified = states.get("verified", 0)
    entries = []
    latest = findings.latest_finding_per_trap(context.site())
    for order in orders.open_orders(context.site()):
        station = register.find(order.tag)
        found = latest.get(order.tag)
        if station is None or found is None:
            continue
        surveyed_on, finding = found
        entries.append((station, surveyed_on, finding.annual_cost, finding.pounds_per_hour))
    backlog = Money.zero()
    for accrual in accrue_all(entries, as_at=day):
        backlog = backlog + accrual.cost
    card = build_scorecard(
        context.site(),
        day.isoformat(),
        reference,
        coverage=survey.coverage(register).assessed_fraction,
        failure_rate=diagnosis.failure_rate,
        annual_cost=losses.total_cost,
        jobs_raised=raised,
        jobs_verified=verified,
        backlog_cost=backlog,
        programme_compliance=schedule.compliance_on(day),
        never_surveyed=len(schedule.never_surveyed()),
    )
    emit_lines(context, card.lines(), card.as_dict())


@programme_group.command("reliability")
@click.option(
    "--by",
    type=click.Choice(["model", "principle", "service", "pressure"]),
    default="model",
    show_default=True,
    help="Which way to cut the failure history.",
)
@click.pass_obj
def programme_reliability(context: Context, by: str) -> None:
    """Failure rates cut by what was fitted and where."""

    register = register_for(context)
    history = FindingRepository(context.book).all_verdicts_per_trap(context.site())
    report = build_reliability(register, history)
    cuts = {
        "model": report.by_model,
        "principle": report.by_principle,
        "service": report.by_service,
        "pressure": report.by_pressure,
    }[by]
    emit_rows(
        context,
        [Column(by), Column.number("assessed"), Column.number("failed"), Column.number("rate")],
        [
            (
                rate.label,
                rate.assessed,
                rate.failed,
                f"{rate.rate:.0%}" if rate.is_reportable else "n/a",
            )
            for rate in cuts
        ],
        keys=[by, "assessed", "failed", "rate"],
        empty="nothing costed yet",
    )


@programme_group.command("repeat-offenders")
@click.option("--at-least", default=2, show_default=True, help="Failures to qualify.")
@click.pass_obj
def programme_repeat(context: Context, at_least: int) -> None:
    """Stations that keep failing whatever is fitted to them."""

    register = register_for(context)
    history = FindingRepository(context.book).all_verdicts_per_trap(context.site())
    report = build_reliability(register, history)
    wanted = set(report.stations_failing_at_least(at_least))
    emit_rows(
        context,
        [Column("tag"), Column.number("failures")],
        [(str(tag), count) for tag, count in report.repeat_offenders if tag in wanted],
        keys=["tag", "failures"],
        empty="no station has failed that often",
    )
