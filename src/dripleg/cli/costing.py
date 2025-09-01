"""`dripleg prices` and `dripleg loss`."""

from __future__ import annotations

import datetime as dt

import click

from dripleg.cli.context import Context
from dripleg.cli.output import emit_facts, emit_lines, emit_rows
from dripleg.diagnosis.batch import diagnose_survey
from dripleg.loss.cost import CostBasis
from dripleg.loss.emissions import FACTORS, factor_named
from dripleg.loss.energy import EnergyModel
from dripleg.loss.register import LossRegister, build_loss_register
from dripleg.repair.recommend import RepairBasis
from dripleg.report.loss_report import build_loss_report
from dripleg.report.table import Column
from dripleg.store.basis_repo import BasisRepository, SiteBasis
from dripleg.store.finding_repo import FindingRepository
from dripleg.store.station_repo import StationRepository
from dripleg.store.survey_repo import SurveyRepository
from dripleg.units.money import Money, Price
from dripleg.units.temperature import Temperature

__all__ = ["loss_group", "prices_group"]


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
@click.option("--feedwater-f", default=227.0, show_default=True, type=float)
@click.option("--efficiency", default=0.82, show_default=True, type=float)
@click.option("--condensate-returned", default=0.75, show_default=True, type=float)
@click.option("--vent-fraction", default=0.35, show_default=True, type=float)
@click.option(
    "--fuel-type",
    type=click.Choice(sorted(FACTORS)),
    default="natural_gas",
    show_default=True,
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


def _register_for(context: Context, reference: str) -> LossRegister:
    register = StationRepository(context.book).load_register(context.site())
    survey = SurveyRepository(context.book).get(context.site(), reference)
    basis = BasisRepository(context.book).get_or_default(context.site())
    return build_loss_register(
        register,
        diagnose_survey(register, survey),
        basis.energy,
        basis.costs,
        basis.factor,
    )


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

    register = _register_for(context, reference)
    if save:
        FindingRepository(context.book).save_register(context.site(), register)
    report = build_loss_report(register, top)
    emit_lines(context, report.lines(), report.as_dict())


@loss_group.command("top")
@click.option("--limit", default=10, show_default=True)
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
