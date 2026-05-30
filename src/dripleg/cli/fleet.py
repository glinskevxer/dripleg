"""`dripleg fleet`: every site on one book, side by side.

A contractor running six plants off one book wants the comparison, and the
comparison is the thing a per site command cannot give. It is deliberately
shallow: counts, the last survey, what it found and what it cost. Anything
deeper differs enough between plants that comparing it is misleading, and the
per site reports are one option away.
"""

from __future__ import annotations

import click

from dripleg.cli.context import Context
from dripleg.cli.output import emit_rows
from dripleg.report.table import Column
from dripleg.store.finding_repo import FindingRepository, WorkOrderRepository
from dripleg.store.plant_repo import PlantRepository
from dripleg.store.station_repo import StationRepository
from dripleg.store.survey_repo import SurveyRepository
from dripleg.units.money import Money

__all__ = ["fleet_group"]


@click.group("fleet")
def fleet_group() -> None:
    """Every site on this book, side by side."""


@fleet_group.command("sites")
@click.pass_obj
def fleet_sites(context: Context) -> None:
    """One row per site: what is on it and what the last survey found."""

    plant = PlantRepository(context.book)
    stations = StationRepository(context.book)
    surveys = SurveyRepository(context.book)
    findings = FindingRepository(context.book)
    orders = WorkOrderRepository(context.book)
    rows = []
    for site in plant.list_sites():
        code = str(site.code)
        references = surveys.list_references(code)
        last = references[-1] if references else ""
        register = stations.load_register(code)
        stored = findings.for_survey(code, last) if last else []
        failing = len([f for f in stored if f.diagnosed.is_failure])
        cost = findings.total_cost(code, last) if last else Money.zero()
        rows.append(
            (
                code,
                site.name,
                len(register),
                len(references),
                last,
                failing,
                str(cost),
                len(orders.open_orders(code)),
            )
        )
    emit_rows(
        context,
        [
            Column("site"),
            Column("name"),
            Column.number("traps"),
            Column.number("surveys"),
            Column("last"),
            Column.number("failing"),
            Column.number("a year"),
            Column.number("open jobs"),
        ],
        rows,
        keys=["site", "name", "traps", "surveys", "last_survey", "failing", "annual", "open_jobs"],
        empty="this book holds no sites",
    )


@fleet_group.command("total")
@click.pass_obj
def fleet_total(context: Context) -> None:
    """The whole book added up, which is the number a group report wants."""

    plant = PlantRepository(context.book)
    stations = StationRepository(context.book)
    surveys = SurveyRepository(context.book)
    findings = FindingRepository(context.book)
    orders = WorkOrderRepository(context.book)
    traps = 0
    costed = Money.zero()
    failing = 0
    open_jobs = 0
    sites = plant.list_sites()
    for site in sites:
        code = str(site.code)
        traps += len(stations.load_register(code))
        references = surveys.list_references(code)
        if references:
            last = references[-1]
            costed = costed + findings.total_cost(code, last)
            failing += len([f for f in findings.for_survey(code, last) if f.diagnosed.is_failure])
        open_jobs += len(orders.open_orders(code))
    emit_rows(
        context,
        [Column("measure"), Column.number("value")],
        [
            ("sites", len(sites)),
            ("trap stations", traps),
            ("failing at the last survey", failing),
            ("annual loss", str(costed)),
            ("open jobs", open_jobs),
        ],
        keys=["measure", "value"],
        empty="this book holds no sites",
    )
