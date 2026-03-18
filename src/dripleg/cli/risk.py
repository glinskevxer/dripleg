"""`dripleg risk`: the findings the plant has decided to live with."""

from __future__ import annotations

import datetime as dt

import click

from dripleg.cli.context import Context
from dripleg.cli.output import emit_facts, emit_rows
from dripleg.model.calendar import add_months
from dripleg.model.tags import TrapTag
from dripleg.report.table import Column
from dripleg.store.risk_repo import DEFAULT_REVIEW_MONTHS, AcceptedRisk, RiskRepository

__all__ = ["risk_group"]


@click.group("risk")
def risk_group() -> None:
    """Accepted findings: what is not being fixed, and when it comes back."""


@risk_group.command("accept")
@click.argument("tag")
@click.option("--reason", required=True, help="Why this one is not being fixed.")
@click.option("--by", "accepted_by", required=True, help="Who made the decision.")
@click.option("--on", default=None, help="The day the decision was made.")
@click.option(
    "--months",
    default=DEFAULT_REVIEW_MONTHS,
    show_default=True,
    type=int,
    help="How long before it comes back on the list.",
)
@click.pass_obj
def risk_accept(
    context: Context,
    tag: str,
    reason: str,
    accepted_by: str,
    on: str | None,
    months: int,
) -> None:
    """Take a trap off the work list until a review date."""

    accepted_on = dt.date.fromisoformat(on) if on is not None else dt.date.today()
    risk = AcceptedRisk(
        tag=TrapTag.parse(tag),
        reason=reason,
        accepted_by=accepted_by,
        accepted_on=accepted_on,
        review_on=add_months(accepted_on, months),
    )
    RiskRepository(context.book).accept(context.site(), risk)
    emit_facts(
        context,
        {
            "tag": str(risk.tag),
            "reason": risk.reason,
            "accepted_by": risk.accepted_by,
            "accepted_on": risk.accepted_on.isoformat(),
            "review_on": risk.review_on.isoformat(),
            "days_left": risk.days_left_on(accepted_on),
        },
    )


@risk_group.command("withdraw")
@click.argument("tag")
@click.pass_obj
def risk_withdraw(context: Context, tag: str) -> None:
    """Put a trap back on the work list before its review date."""

    was_accepted = RiskRepository(context.book).withdraw(context.site(), tag)
    emit_facts(context, {"tag": tag.upper(), "was_accepted": was_accepted})


@risk_group.command("list")
@click.option("--on", default=None, help="The day to judge the review dates against.")
@click.option("--due-only", is_flag=True, help="Only the ones past their review date.")
@click.pass_obj
def risk_list(context: Context, on: str | None, due_only: bool) -> None:
    """Every acceptance, soonest review first."""

    day = dt.date.fromisoformat(on) if on is not None else dt.date.today()
    repo = RiskRepository(context.book)
    risks = repo.due_for_review(context.site(), day) if due_only else repo.all_for(context.site())
    emit_rows(
        context,
        [
            Column("tag"),
            Column("by"),
            Column("accepted"),
            Column("review"),
            Column.number("days left"),
            Column("state"),
            Column("reason", max_width=40),
        ],
        [
            (
                str(risk.tag),
                risk.accepted_by,
                risk.accepted_on.isoformat(),
                risk.review_on.isoformat(),
                risk.days_left_on(day),
                "live" if risk.is_live_on(day) else "due",
                risk.reason,
            )
            for risk in risks
        ],
        keys=["tag", "accepted_by", "accepted_on", "review_on", "days_left", "state", "reason"],
        empty="nothing has been accepted",
    )
