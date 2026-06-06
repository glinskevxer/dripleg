"""`dripleg prices` and `dripleg loss`."""

from __future__ import annotations

import csv
import datetime as dt
import sys

import click

from dripleg.cli.context import Context
from dripleg.cli.loading import loss_register_for
from dripleg.cli.output import emit_facts, emit_lines, emit_rows
from dripleg.loss.cost import CostBasis
from dripleg.loss.emissions import FACTORS, factor_named
from dripleg.loss.energy import EnergyModel
from dripleg.repair.recommend import RepairBasis
from dripleg.report.energy_report import build_energy_report
from dripleg.report.loss_report import build_loss_report
from dripleg.report.table import Column
from dripleg.store.basis_repo import BasisRepository, SiteBasis
from dripleg.store.finding_repo import FindingRepository
from dripleg.units.money import Money, Price
from dripleg.units.temperature import Temperature

__all__ = ["LOSS_COLUMNS", "loss_group", "prices_group"]

LOSS_COLUMNS = (
    "tag",
    "area",
    "service",
    "condition",
    "confidence",
    "rules",
    "pounds_per_hour",
    "pounds_per_year",
    "fuel_mmbtu_per_year",
    "tonnes_co2e",
    "fuel_cents",
    "water_side_cents",
    "annual_cents",
    "share_of_total",
)


@click.group("prices")
def prices_group() -> None:
    """What the boiler house costs this year."""


@prices_group.command("set")
@click.option("--fuel", required=True, help="Dollars per MMBtu.")
@click.option("--water", default="4.10", show_default=True, help="Dollars per 1000 gal.")
@click.option("--effluent", default="3.40", show_default=True, help="Dollars per 1000 gal.")
@click.option("--chemical", default="2.75", show_default=True, help="Dollars per 1000 gal.")
@click.option("--labour", default="74.00", show_default=True, help="Dollars per hour.")
@click.option("--permit", default="120.00", show_default=True, help="Dollars per permit job.")
@click.option(
    "--feedwater-f",
    default=227.0,
    show_default=True,
    type=float,
    help="Deaerator temperature the makeup arrives at.",
)
@click.option(
    "--efficiency",
    default=0.82,
    show_default=True,
    type=float,
    help="Boiler efficiency, as a fraction.",
)
@click.option(
    "--condensate-returned",
    default=0.75,
    show_default=True,
    type=float,
    help="Share of the condensate that comes back.",
)
@click.option(
    "--vent-fraction",
    default=0.35,
    show_default=True,
    type=float,
    help="Share of live steam into the return that the receiver vents.",
)
@click.option(
    "--fuel-type",
    type=click.Choice(sorted(FACTORS)),
    default="natural_gas",
    show_default=True,
    help="Which emissions factor the carbon figure uses.",
)
@click.option("--from", "effective_from", default=None, help="Date these took effect.")
@click.pass_obj
def prices_set(
    context: Context,
    fuel: str,
    water: str,
    effluent: str,
    chemical: str,
    labour: str,
    permit: str,
    feedwater_f: float,
    efficiency: float,
    condensate_returned: float,
    vent_fraction: float,
    fuel_type: str,
    effective_from: str | None,
) -> None:
    """Write the numbers every costing at this site reads."""

    basis = SiteBasis(
        costs=CostBasis(
            fuel=Price.of(fuel, "MMBtu"),
            water=Price.of(water, "1000 gal"),
            effluent=Price.of(effluent, "1000 gal"),
            chemical=Price.of(chemical, "1000 gal"),
        ),
        energy=EnergyModel(
            feedwater_temperature=Temperature.from_fahrenheit(feedwater_f),
            boiler_efficiency=efficiency,
            condensate_returned=condensate_returned,
            receiver_vent_fraction=vent_fraction,
        ),
        repairs=RepairBasis(labour=Price.of(labour, "h"), permit_cost=Money.parse(permit)),
        factor=factor_named(fuel_type),
        effective_from=(
            dt.date.fromisoformat(effective_from) if effective_from is not None else dt.date.today()
        ),
    )
    BasisRepository(context.book).save(context.site(), basis)
    emit_facts(context, basis.facts())


@prices_group.command("show")
@click.pass_obj
def prices_show(context: Context) -> None:
    """The numbers in force, or the worked example if none are set."""

    emit_facts(context, BasisRepository(context.book).get_or_default(context.site()).facts())


@click.group("loss")
def loss_group() -> None:
    """What the failed traps are costing."""


@loss_group.command("report")
@click.argument("reference")
@click.option("--top", default=10, show_default=True, help="How many traps to name.")
@click.option("--save", is_flag=True, help="Write the findings back to the book.")
@click.pass_obj
def loss_report(context: Context, reference: str, top: int, save: bool) -> None:
    """Cost a survey and print the register."""

    register = loss_register_for(context, reference)
    if save:
        FindingRepository(context.book).save_register(context.site(), register)
    report = build_loss_report(register, top)
    emit_lines(context, report.lines(), report.as_dict())


@loss_group.command("top")
@click.option("--limit", default=10, show_default=True, help="How many to name.")
@click.pass_obj
def loss_top(context: Context, limit: int) -> None:
    """The dearest traps across every survey saved on the book."""

    findings = FindingRepository(context.book).dearest(context.site(), limit)
    emit_rows(
        context,
        [
            Column("tag"),
            Column("survey"),
            Column("condition"),
            Column.number("lb/h"),
            Column.number("a year"),
        ],
        [
            (
                str(f.tag),
                f.survey_reference,
                f.diagnosed.label,
                f"{f.pounds_per_hour:,.1f}",
                str(f.annual_cost),
            )
            for f in findings
        ],
        keys=["tag", "survey", "condition", "pounds_per_hour", "annual"],
        empty="nothing costed yet",
    )


@loss_group.command("energy")
@click.argument("reference")
@click.option("--top", default=10, show_default=True, help="How many traps to name.")
@click.pass_obj
def loss_energy(context: Context, reference: str, top: int) -> None:
    """The steam, fuel and carbon a survey found, rather than the money."""

    report = build_energy_report(loss_register_for(context, reference), top)
    emit_lines(context, report.lines(), report.as_dict())


@loss_group.command("export")
@click.argument("reference")
@click.option("--losing-only", is_flag=True, help="Leave the healthy traps out.")
@click.pass_obj
def loss_export(context: Context, reference: str, losing_only: bool) -> None:
    """Write the costed register out as csv for a spreadsheet to argue with."""

    register = loss_register_for(context, reference)
    rows = register.losing if losing_only else register.rows
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(LOSS_COLUMNS)
    for row in rows:
        writer.writerow(
            [
                str(row.tag),
                str(row.area),
                row.service.value,
                row.condition.value,
                f"{row.diagnosis.confidence:.3f}",
                "|".join(row.diagnosis.evidence.rules_fired),
                f"{row.steam.flow.pounds_per_hour:.2f}",
                f"{row.steam.pounds_per_year:.0f}",
                f"{row.heat.mmbtu_per_year:.2f}",
                f"{row.stack.tonnes_co2e:.3f}",
                row.cost.fuel.cents,
                row.cost.water_side.cents,
                row.annual_cost.cents,
                f"{register.share_of_total(row):.4f}",
            ]
        )


@loss_group.command("trap")
@click.argument("tag")
@click.pass_obj
def loss_trap(context: Context, tag: str) -> None:
    """Every costed finding on one trap, oldest first."""

    findings = FindingRepository(context.book).history_for(context.site(), tag)
    emit_rows(
        context,
        [
            Column("survey"),
            Column("field code"),
            Column("rules said"),
            Column.number("confidence"),
            Column.number("a year"),
        ],
        [
            (
                f.survey_reference,
                f.reported.label,
                f.diagnosed.label,
                f"{f.confidence:.0%}",
                str(f.annual_cost),
            )
            for f in findings
        ],
        keys=["survey", "field", "rules", "confidence", "annual"],
        empty="nothing costed on that trap",
    )
