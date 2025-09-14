"""`dripleg work`: the ranked list, and the orders that come off it."""

from __future__ import annotations

import datetime as dt

import click

from dripleg.cli.context import Context
from dripleg.cli.loading import work_list_for
from dripleg.cli.output import emit_facts, emit_lines, emit_rows
from dripleg.errors import ConflictError
from dripleg.repair.priority import Priority
from dripleg.repair.workorder import WorkOrder
from dripleg.report.table import Column
from dripleg.report.work_report import build_work_report
from dripleg.store.finding_repo import WorkOrderRepository
from dripleg.units.money import Money

__all__ = ["work_group"]


@click.group("work")
def work_group() -> None:
    """The repair list and the orders raised from it."""


@work_group.command("list")
@click.argument("reference")
@click.option("--budget", default=None, help="Draw a line where the money runs out.")
@click.option(
    "--band",
    default=None,
    type=click.Choice([p.value for p in Priority]),
    help="Only this priority band.",
)
@click.pass_obj
def work_list(context: Context, reference: str, budget: str | None, band: str | None) -> None:
    """The ranked repair list off one survey."""

    report = build_work_report(
        context.site(),
        work_list_for(context, reference),
        None if budget is None else Money.parse(budget),
        None if band is None else Priority(band),
    )
    emit_lines(context, report.lines(), report.as_dict())


@work_group.command("raise")
@click.argument("reference")
@click.option("--budget", default=None, help="Only raise what fits.")
@click.option("--on", default=None, help="The day the orders are raised.")
@click.option("--prefix", default="WO", show_default=True, help="Work order number prefix.")
@click.pass_obj
def work_raise(
    context: Context, reference: str, budget: str | None, on: str | None, prefix: str
) -> None:
    """Raise a work order for every job on the list, in rank order."""

    work = work_list_for(context, reference)
    jobs = work.actionable
    if budget is not None:
        jobs, _ = work.within(Money.parse(budget))
    raised_on = dt.date.fromisoformat(on) if on is not None else dt.date.today()
    repo = WorkOrderRepository(context.book)
    made: list[tuple[str, str, str, str]] = []
    for job in jobs:
        if any(order.is_open for order in repo.for_tag(context.site(), job.row.tag)):
            continue
        order = WorkOrder.raise_for(
            repo.next_number(context.site(), prefix),
            job.job,
            on=raised_on,
            within_days=job.priority.within_days,
        )
        repo.save(context.site(), order)
        made.append((order.number, str(order.tag), order.action.label, order.due_on.isoformat()))
    emit_rows(
        context,
        [Column("number"), Column("tag"), Column("action"), Column("due")],
        made,
        keys=["number", "tag", "action", "due"],
        empty="nothing to raise",
    )


@work_group.command("open")
@click.option("--overdue-on", default=None, help="Only what is late on this day.")
@click.pass_obj
def work_open(context: Context, overdue_on: str | None) -> None:
    """Every order still open."""

    repo = WorkOrderRepository(context.book)
    orders = (
        repo.overdue_on(context.site(), dt.date.fromisoformat(overdue_on))
        if overdue_on is not None
        else repo.open_orders(context.site())
    )
    emit_rows(
        context,
        [
            Column("number"),
            Column("tag"),
            Column("action"),
            Column("state"),
            Column("due"),
            Column("with"),
        ],
        [
            (
                o.number,
                str(o.tag),
                o.action.label,
                o.state.label,
                o.due_on.isoformat(),
                o.assigned_to or "",
            )
            for o in orders
        ],
        keys=["number", "tag", "action", "state", "due", "assigned_to"],
        empty="nothing open",
    )


@work_group.command("issue")
@click.argument("number")
@click.option("--to", "assignee", required=True, help="Who is doing it.")
@click.option("--on", default=None, help="The day it was issued.")
@click.pass_obj
def work_issue(context: Context, number: str, assignee: str, on: str | None) -> None:
    """Issue an order to somebody."""

    _move(context, number, "issue", on, assignee=assignee)


@work_group.command("start")
@click.argument("number")
@click.option("--on", default=None)
@click.pass_obj
def work_start(context: Context, number: str, on: str | None) -> None:
    """Mark an order as started."""

    _move(context, number, "start", on)


@work_group.command("complete")
@click.argument("number")
@click.option("--on", default=None)
@click.option("--cost", default=None, help="What it actually cost.")
@click.pass_obj
def work_complete(context: Context, number: str, on: str | None, cost: str | None) -> None:
    """Mark the work finished. This is not the end of the order."""

    _move(context, number, "complete", on, cost=cost)


@work_group.command("verify")
@click.argument("number")
@click.option("--on", default=None, help="The day the retest was taken.")
@click.pass_obj
def work_verify(context: Context, number: str, on: str | None) -> None:
    """Close an order on a retest, which is the only way it closes."""

    _move(context, number, "verify", on)


def _move(
    context: Context,
    number: str,
    step: str,
    on: str | None,
    *,
    assignee: str | None = None,
    cost: str | None = None,
) -> None:
    repo = WorkOrderRepository(context.book)
    order = repo.get(number)
    day = dt.date.fromisoformat(on) if on is not None else dt.date.today()
    if step == "issue":
        if assignee is None:
            raise ConflictError("say who the order is issued to")
        order.issue(assignee, day)
    elif step == "start":
        order.start(day)
    elif step == "complete":
        order.complete(day, None if cost is None else Money.parse(cost))
    else:
        order.verify(day)
    repo.save(context.site(), order)
    emit_facts(
        context,
        {
            "number": order.number,
            "tag": str(order.tag),
            "action": order.action.label,
            "state": order.state.label,
            "assigned_to": order.assigned_to or "",
            "due_on": order.due_on.isoformat(),
            "completed_on": "" if order.completed_on is None else order.completed_on.isoformat(),
            "verified_on": "" if order.verified_on is None else order.verified_on.isoformat(),
            "estimated": str(order.estimated_cost),
            "actual": "" if order.actual_cost is None else str(order.actual_cost),
            "history": list(order.history),
        },
    )
