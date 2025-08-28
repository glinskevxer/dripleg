"""`dripleg trap`: the stations, and what is fitted to them."""

from __future__ import annotations

import datetime as dt

import click

from dripleg.cli.context import Context
from dripleg.cli.output import emit_facts, emit_rows
from dripleg.model.attributes import Accessibility, Criticality, ServiceType
from dripleg.model.header import DischargeDestination
from dripleg.model.installation import TrapInstallation
from dripleg.model.tags import SiteCode, TrapTag
from dripleg.report.table import Column
from dripleg.store.catalogue_repo import CatalogueRepository, ProfileRepository
from dripleg.store.plant_repo import PlantRepository
from dripleg.store.station_repo import StationRepository

__all__ = ["trap_group"]


@click.group("trap")
def trap_group() -> None:
    """Trap stations: one row per place a trap is fitted."""


@trap_group.command("add")
@click.argument("tag")
@click.option("--model", "model_code", required=True, help="Maker and code, as 'Halden/TD52'.")
@click.option(
    "--service",
    type=click.Choice([s.value for s in ServiceType]),
    default=ServiceType.DRIP.value,
    show_default=True,
)
@click.option(
    "--access",
    type=click.Choice([a.value for a in Accessibility]),
    default=Accessibility.GROUND_LEVEL.value,
    show_default=True,
)
@click.option(
    "--criticality",
    type=click.Choice([c.value for c in Criticality]),
    default=Criticality.NUISANCE.value,
    show_default=True,
)
@click.option("--profile", "profile_code", default="CONT", show_default=True)
@click.option("--installed", required=True, help="Date the fitted trap went in.")
@click.option(
    "--to",
    "destination",
    type=click.Choice([d.value for d in DischargeDestination]),
    default=None,
    help="Overrides the header's destination.",
)
@click.option("--no-strainer", is_flag=True, help="No strainer ahead of the trap.")
@click.option("--valves", default=2, show_default=True, type=int)
@click.option("--interval", default=None, type=int, help="Survey interval override, months.")
@click.option("--note", default="", help="Anything the crew needs to know.")
@click.pass_obj
def trap_add(
    context: Context,
    tag: str,
    model_code: str,
    service: str,
    access: str,
    criticality: str,
    profile_code: str,
    installed: str,
    destination: str | None,
    no_strainer: bool,
    valves: int,
    interval: int | None,
    note: str,
) -> None:
    """Add a trap station, or update the one that is there."""

    parsed = TrapTag.parse(tag)
    manufacturer, _, code = model_code.partition("/")
    plant = PlantRepository(context.book)
    station = TrapInstallation(
        site=SiteCode.parse(context.site()),
        tag=parsed,
        header=plant.get_header(context.site(), parsed.area, parsed.system),
        model=CatalogueRepository(context.book).get(manufacturer, code or manufacturer),
        service=ServiceType(service),
        accessibility=Accessibility(access),
        criticality=Criticality(criticality),
        profile=ProfileRepository(context.book).get(context.site(), profile_code),
        installed_on=dt.date.fromisoformat(installed),
        destination=None if destination is None else DischargeDestination(destination),
        strainer_fitted=not no_strainer,
        isolation_valves=valves,
        interval_months_override=interval,
        note=note,
    )
    StationRepository(context.book).save(station)
    emit_facts(context, _facts(station))


@trap_group.command("list")
@click.option("--area", default=None, help="Only this area.")
@click.option("--service", default=None, type=click.Choice([s.value for s in ServiceType]))
@click.option("--live", is_flag=True, help="Only traps still in service today.")
@click.pass_obj
def trap_list(context: Context, area: str | None, service: str | None, live: bool) -> None:
    """Every trap station at a site."""

    register = StationRepository(context.book).load_register(context.site())
    stations = list(register)
    if area is not None:
        stations = register.in_area(area)
    if service is not None:
        stations = [s for s in stations if s.service is ServiceType(service)]
    if live:
        today = dt.date.today()
        stations = [s for s in stations if s.is_in_service_on(today)]
    emit_rows(
        context,
        [
            Column("tag"),
            Column("service"),
            Column("model"),
            Column("access"),
            Column("criticality"),
            Column.number("months"),
        ],
        [
            (
                str(s.tag),
                s.service.label,
                f"{s.model.manufacturer} {s.model.code}",
                s.accessibility.value,
                s.criticality.value,
                s.survey_interval_months,
            )
            for s in stations
        ],
        keys=["tag", "service", "model", "access", "criticality", "interval_months"],
        empty="no traps yet",
    )


@trap_group.command("show")
@click.argument("tag")
@click.pass_obj
def trap_show(context: Context, tag: str) -> None:
    """Everything on one station."""

    station = StationRepository(context.book).get(context.site(), tag)
    emit_facts(context, _facts(station))


@trap_group.command("retire")
@click.argument("tag")
@click.option("--on", required=True, help="The day it came out.")
@click.pass_obj
def trap_retire(context: Context, tag: str, on: str) -> None:
    """Take a station out of service."""

    repo = StationRepository(context.book)
    station = repo.get(context.site(), tag)
    retired = station.retired_on(dt.date.fromisoformat(on))
    repo.save(retired)
    emit_facts(context, _facts(retired))


@trap_group.command("refit")
@click.argument("tag")
@click.option("--model", "model_code", required=True, help="Maker and code, as 'Halden/TD75'.")
@click.option("--on", required=True, help="The day the new trap went in.")
@click.pass_obj
def trap_refit(context: Context, tag: str, model_code: str, on: str) -> None:
    """Put a different trap on the same station."""

    repo = StationRepository(context.book)
    station = repo.get(context.site(), tag)
    manufacturer, _, code = model_code.partition("/")
    model = CatalogueRepository(context.book).get(manufacturer, code or manufacturer)
    refitted = station.replaced_with(model, dt.date.fromisoformat(on))
    repo.save(refitted)
    emit_facts(context, _facts(refitted))


def _facts(station: TrapInstallation) -> dict[str, object]:
    return {
        "tag": str(station.tag),
        "header": f"{station.header.area}-{station.header.system} {station.header.name}",
        "pressure": str(station.header.operating_pressure),
        "model": f"{station.model.manufacturer} {station.model.code}",
        "principle": station.model.principle.label,
        "service": station.service.label,
        "access": station.accessibility.value,
        "criticality": station.criticality.value,
        "discharges_to": station.discharge_destination.value,
        "profile": station.profile.code,
        "installed_on": station.installed_on.isoformat(),
        "removed_on": "" if station.removed_on is None else station.removed_on.isoformat(),
        "interval_months": station.survey_interval_months,
        "can_be_isolated": station.can_be_isolated,
        "note": station.note,
    }
