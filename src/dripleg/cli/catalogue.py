"""`dripleg model` and `dripleg profile`."""

from __future__ import annotations

import click

from dripleg.cli.context import Context
from dripleg.cli.output import emit_facts, emit_rows
from dripleg.model.catalogue import ConnectionType, TrapModel
from dripleg.model.operating import OperatingProfile, ServicePattern
from dripleg.model.principles import OperatingPrinciple
from dripleg.report.table import Column
from dripleg.store.catalogue_repo import CatalogueRepository, ProfileRepository
from dripleg.store.codes import months_from_text, months_to_text
from dripleg.units.money import Money
from dripleg.units.pressure import Pressure

__all__ = ["model_group", "profile_group"]


@click.group("model")
def model_group() -> None:
    """Trap models: what the storeroom stocks."""


@model_group.command("add")
@click.argument("manufacturer")
@click.argument("code")
@click.option(
    "--principle",
    required=True,
    type=click.Choice([p.value for p in OperatingPrinciple]),
    help="How the trap works.",
)
@click.option("--orifice", required=True, type=float, help="Orifice diameter in inches.")
@click.option("--pmo", required=True, type=float, help="Maximum operating pressure, psig.")
@click.option(
    "--back-pressure",
    default=80.0,
    show_default=True,
    type=float,
    help="Highest back pressure as a percentage of inlet.",
)
@click.option("--size", default=0.5, show_default=True, type=float, help="Connection, inches.")
@click.option(
    "--connection",
    type=click.Choice(sorted(ConnectionType.ALL)),
    default=ConnectionType.SCREWED,
    show_default=True,
    help="How it joins the pipe.",
)
@click.option("--price", required=True, help="List price in dollars.")
@click.option("--discontinued", is_flag=True, help="No longer bought.")
@click.option("--replaced-by", default=None, help="What took its place.")
@click.pass_obj
def model_add(
    context: Context,
    manufacturer: str,
    code: str,
    principle: str,
    orifice: float,
    pmo: float,
    back_pressure: float,
    size: float,
    connection: str,
    price: str,
    discontinued: bool,
    replaced_by: str | None,
) -> None:
    """Add a trap model, or update the one that is there."""

    model = TrapModel(
        manufacturer=manufacturer,
        code=code,
        principle=OperatingPrinciple(principle),
        orifice_diameter_in=orifice,
        max_operating_pressure=Pressure.from_psig(pmo),
        max_back_pressure_percent=back_pressure,
        connection_size_in=size,
        connection_type=connection,
        list_price=Money.parse(price),
        discontinued=discontinued,
        replaced_by=replaced_by,
    )
    CatalogueRepository(context.book).save(model)
    emit_facts(
        context,
        {
            "manufacturer": model.manufacturer,
            "code": model.code,
            "principle": model.principle.label,
            "orifice_in": model.orifice_diameter_in,
            "pmo_psig": round(model.max_operating_pressure.psig, 1),
            "price": str(model.list_price),
            "orderable": model.is_orderable(),
        },
    )


@model_group.command("list")
@click.option(
    "--principle",
    default=None,
    type=click.Choice([p.value for p in OperatingPrinciple]),
    help="Only models that work this way.",
)
@click.pass_obj
def model_list(context: Context, principle: str | None) -> None:
    """Every model in the catalogue."""

    catalogue = CatalogueRepository(context.book).load_catalogue()
    models = (
        catalogue.with_principle(OperatingPrinciple(principle))
        if principle is not None
        else list(catalogue)
    )
    emit_rows(
        context,
        [
            Column("maker"),
            Column("code"),
            Column("principle"),
            Column.number("orifice"),
            Column.number("pmo"),
            Column.number("price"),
            Column("stocked"),
        ],
        [
            (
                m.manufacturer,
                m.code,
                m.principle.label,
                f"{m.orifice_diameter_in:.3f}",
                f"{m.max_operating_pressure.psig:.0f}",
                str(m.list_price),
                "yes" if m.is_orderable() else "no",
            )
            for m in models
        ],
        keys=["manufacturer", "code", "principle", "orifice_in", "pmo_psig", "price", "stocked"],
        empty="no models yet",
    )


@click.group("profile")
def profile_group() -> None:
    """Operating profiles: when a leg is live."""


@profile_group.command("add")
@click.argument("code")
@click.argument("name")
@click.option(
    "--pattern",
    type=click.Choice([p.value for p in ServicePattern]),
    default=ServicePattern.CONTINUOUS.value,
    show_default=True,
    help="The shape of the year this leg runs.",
)
@click.option(
    "--load-factor",
    default=1.0,
    show_default=True,
    type=float,
    help="Share of the live hours it actually carries steam.",
)
@click.option("--months", default="", help="Campaign months, as 9,10,11.")
@click.pass_obj
def profile_add(
    context: Context,
    code: str,
    name: str,
    pattern: str,
    load_factor: float,
    months: str,
) -> None:
    """Add an operating profile to a site."""

    profile = OperatingProfile(
        code=code,
        name=name,
        pattern=ServicePattern(pattern),
        load_factor=load_factor,
        campaign_months=months_from_text(months),
    )
    ProfileRepository(context.book).save(context.site(), profile)
    emit_facts(
        context,
        {
            "code": profile.code,
            "name": profile.name,
            "pattern": profile.pattern.value,
            "load_factor": profile.load_factor,
            "months": months_to_text(profile.live_months),
            "hours_per_year": round(profile.annual_hours()),
        },
    )


@profile_group.command("list")
@click.pass_obj
def profile_list(context: Context) -> None:
    """Every operating profile at a site."""

    profiles = ProfileRepository(context.book).list_for(context.site())
    emit_rows(
        context,
        [
            Column("code"),
            Column("name"),
            Column("pattern"),
            Column.number("load"),
            Column.number("h/y"),
        ],
        [
            (
                p.code,
                p.name,
                p.pattern.value,
                f"{p.load_factor:.2f}",
                f"{p.annual_hours():,.0f}",
            )
            for p in profiles
        ],
        keys=["code", "name", "pattern", "load_factor", "hours_per_year"],
        empty="no profiles yet",
    )
