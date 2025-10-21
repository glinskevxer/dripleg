"""`dripleg site`, `dripleg area` and `dripleg header`."""

from __future__ import annotations

import click

from dripleg.cli.context import Context
from dripleg.cli.output import emit_facts, emit_rows
from dripleg.model.header import DischargeDestination, SteamHeader
from dripleg.model.plant import Area, Site
from dripleg.report.table import Column
from dripleg.store.plant_repo import PlantRepository

__all__ = ["area_group", "header_group", "site_group"]


@click.group("site")
def site_group() -> None:
    """Sites: the plants this book covers."""


@site_group.command("add")
@click.argument("code")
@click.argument("name")
@click.option("--operator", required=True, help="Who runs the plant.")
@click.option("--start-month", default=1, show_default=True, help="Programme year start month.")
@click.option(
    "--fuel-basis",
    default="delivered natural gas",
    show_default=True,
    help="What the fuel price on this site is quoted for.",
)
@click.pass_obj
def site_add(
    context: Context,
    code: str,
    name: str,
    operator: str,
    start_month: int,
    fuel_basis: str,
) -> None:
    """Add a site, or update the one that is already there."""

    site = Site.of(
        code, name, operator, programme_start_month=start_month, fuel_price_basis=fuel_basis
    )
    PlantRepository(context.book).save_site(site)
    emit_facts(
        context,
        {
            "code": str(site.code),
            "name": site.name,
            "operator": site.operator,
            "programme_start_month": site.programme_start_month,
        },
    )


@site_group.command("list")
@click.pass_obj
def site_list(context: Context) -> None:
    """Every site in the book."""

    sites = PlantRepository(context.book).list_sites()
    emit_rows(
        context,
        [Column("code"), Column("name"), Column("operator"), Column.number("start")],
        [(str(s.code), s.name, s.operator, s.programme_start_month) for s in sites],
        keys=["code", "name", "operator", "start_month"],
        empty="no sites yet",
    )


@click.group("area")
def area_group() -> None:
    """Areas: the blocks a site is cut into."""


@area_group.command("add")
@click.argument("code")
@click.argument("name")
@click.option("--cost-centre", required=True, help="Where the loss lands.")
@click.option("--parent", default=None, help="The area this one sits inside.")
@click.pass_obj
def area_add(context: Context, code: str, name: str, cost_centre: str, parent: str | None) -> None:
    """Add an area to a site."""

    area = Area.of(context.site(), code, name, cost_centre, parent=parent)
    PlantRepository(context.book).save_area(area)
    emit_facts(
        context,
        {
            "site": str(area.site),
            "code": str(area.code),
            "name": area.name,
            "cost_centre": area.cost_centre,
            "parent": "" if area.parent is None else str(area.parent),
        },
    )


@area_group.command("list")
@click.pass_obj
def area_list(context: Context) -> None:
    """Every area at a site."""

    areas = PlantRepository(context.book).list_areas(context.site())
    emit_rows(
        context,
        [Column("code"), Column("name"), Column("cost centre"), Column("parent")],
        [
            (str(a.code), a.name, a.cost_centre, "" if a.parent is None else str(a.parent))
            for a in areas
        ],
        keys=["code", "name", "cost_centre", "parent"],
        empty="no areas yet",
    )


@click.group("header")
def header_group() -> None:
    """Headers: the steam mains traps hang off."""


@header_group.command("add")
@click.argument("area")
@click.argument("system")
@click.argument("name")
@click.option("--psig", required=True, type=float, help="Operating pressure.")
@click.option("--design-psig", default=None, type=float, help="Design pressure.")
@click.option(
    "--discharge-psig",
    default=0.0,
    type=float,
    show_default=True,
    help="Pressure the traps on it discharge against.",
)
@click.option(
    "--to",
    "destination",
    type=click.Choice([d.value for d in DischargeDestination]),
    default=DischargeDestination.RETURN_LINE.value,
    show_default=True,
    help="Where the traps on it discharge.",
)
@click.pass_obj
def header_add(
    context: Context,
    area: str,
    system: str,
    name: str,
    psig: float,
    design_psig: float | None,
    discharge_psig: float,
    destination: str,
) -> None:
    """Add a header to an area."""

    repo = PlantRepository(context.book)
    header = SteamHeader.of(
        repo.get_area(context.site(), area),
        system,
        name,
        psig,
        design_psig=design_psig,
        discharge_psig=discharge_psig,
        destination=DischargeDestination(destination),
    )
    repo.save_header(header)
    emit_facts(
        context,
        {
            "area": str(header.area),
            "system": str(header.system),
            "name": header.name,
            "operating": str(header.operating_pressure),
            "saturation_f": round(header.saturation_temperature.fahrenheit, 1),
            "class": header.pressure_class.label,
            "choked": header.discharge_is_choked,
        },
    )


@header_group.command("list")
@click.option("--area", default=None, help="Only this area.")
@click.pass_obj
def header_list(context: Context, area: str | None) -> None:
    """Every header at a site."""

    headers = PlantRepository(context.book).list_headers(context.site(), area)
    emit_rows(
        context,
        [
            Column("area"),
            Column("system"),
            Column("name"),
            Column.number("psig"),
            Column("class"),
            Column("to"),
        ],
        [
            (
                str(h.area),
                str(h.system),
                h.name,
                f"{h.operating_pressure.psig:.1f}",
                h.pressure_class.label,
                h.destination.value,
            )
            for h in headers
        ],
        keys=["area", "system", "name", "psig", "class", "destination"],
        empty="no headers yet",
    )
