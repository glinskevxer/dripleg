"""`dripleg trap`: the stations, and what is fitted to them."""

from __future__ import annotations

import csv
import datetime as dt
import sys
from pathlib import Path

import click

from dripleg.cli.context import Context
from dripleg.cli.loading import register_for
from dripleg.cli.output import emit_facts, emit_rows
from dripleg.ingest.reader import write_quarantine
from dripleg.ingest.register_reader import read_register_csv
from dripleg.model.attributes import Accessibility, Criticality, ServiceType
from dripleg.model.header import DischargeDestination
from dripleg.model.installation import TrapInstallation
from dripleg.model.tags import SiteCode, TrapTag
from dripleg.report.table import Column
from dripleg.sizing.audit import audit_sizing
from dripleg.store.catalogue_repo import CatalogueRepository, ProfileRepository
from dripleg.store.fitting_repo import FittingRepository
from dripleg.store.plant_repo import PlantRepository
from dripleg.store.station_repo import StationRepository
from dripleg.units.temperature import Temperature

__all__ = ["EXPORT_COLUMNS", "trap_group"]

EXPORT_COLUMNS = (
    "tag",
    "manufacturer",
    "model",
    "installed",
    "service",
    "access",
    "criticality",
    "profile",
    "destination",
    "strainer",
    "valves",
    "interval",
    "note",
)


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
    help="What the trap drains.",
)
@click.option(
    "--access",
    type=click.Choice([a.value for a in Accessibility]),
    default=Accessibility.GROUND_LEVEL.value,
    show_default=True,
    help="How much work it is to reach.",
)
@click.option(
    "--criticality",
    type=click.Choice([c.value for c in Criticality]),
    default=Criticality.NUISANCE.value,
    show_default=True,
    help="What it costs the plant if this trap is wrong.",
)
@click.option(
    "--profile",
    "profile_code",
    default="CONT",
    show_default=True,
    help="Operating profile code.",
)
@click.option("--installed", required=True, help="Date the fitted trap went in.")
@click.option(
    "--to",
    "destination",
    type=click.Choice([d.value for d in DischargeDestination]),
    default=None,
    help="Overrides the header's destination.",
)
@click.option("--no-strainer", is_flag=True, help="No strainer ahead of the trap.")
@click.option(
    "--valves",
    default=2,
    show_default=True,
    type=int,
    help="How many isolation valves the station has.",
)
@click.option("--interval", default=None, type=int, help="Survey interval override, months.")
@click.option("--pipe", "pipe_nominal", default=None, help="Nominal pipe size of the run.")
@click.option("--run-ft", default=None, type=float, help="Length of run this trap drains.")
@click.option(
    "--warmup-minutes",
    default=30.0,
    show_default=True,
    type=float,
    help="How long the run takes to come up to temperature.",
)
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
    pipe_nominal: str | None,
    run_ft: float | None,
    warmup_minutes: float,
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
        pipe_nominal=pipe_nominal,
        run_length_ft=run_ft,
        warmup_minutes=warmup_minutes,
        note=note,
    )
    StationRepository(context.book).save(station)
    FittingRepository(context.book).record(
        context.site(), station.tag, station.model, station.installed_on
    )
    emit_facts(context, _facts(station))


@trap_group.command("list")
@click.option("--area", default=None, help="Only this area.")
@click.option(
    "--service",
    default=None,
    type=click.Choice([s.value for s in ServiceType]),
    help="Only traps on this service.",
)
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
@click.option("--work-order", default=None, help="The order that put it in.")
@click.pass_obj
def trap_refit(
    context: Context, tag: str, model_code: str, on: str, work_order: str | None
) -> None:
    """Put a different trap on the same station."""

    repo = StationRepository(context.book)
    station = repo.get(context.site(), tag)
    manufacturer, _, code = model_code.partition("/")
    model = CatalogueRepository(context.book).get(manufacturer, code or manufacturer)
    fitted_on = dt.date.fromisoformat(on)
    refitted = station.replaced_with(model, fitted_on)
    repo.save(refitted)
    FittingRepository(context.book).record(
        context.site(), refitted.tag, model, fitted_on, work_order
    )
    emit_facts(context, _facts(refitted))


@trap_group.command("history")
@click.argument("tag")
@click.pass_obj
def trap_history(context: Context, tag: str) -> None:
    """Every trap that has ever been fitted to one station."""

    fittings = FittingRepository(context.book).history_for(context.site(), tag)
    today = dt.date.today()
    emit_rows(
        context,
        [
            Column("fitted"),
            Column("model"),
            Column("order"),
            Column("warranty ends"),
            Column.number("days in"),
        ],
        [
            (
                fitting.fitted_on.isoformat(),
                f"{fitting.manufacturer} {fitting.model_code}",
                fitting.work_order or "",
                fitting.warranty_ends.isoformat(),
                fitting.age_days_on(today),
            )
            for fitting in fittings
        ],
        keys=["fitted", "model", "work_order", "warranty_ends", "days_in"],
        empty="nothing has ever been fitted to that station",
    )


@trap_group.command("warranty")
@click.option("--on", default=None, help="The day to judge the warranties against.")
@click.pass_obj
def trap_warranty(context: Context, on: str | None) -> None:
    """The traps still inside the warranty they were bought with."""

    day = dt.date.fromisoformat(on) if on is not None else dt.date.today()
    fittings = FittingRepository(context.book).in_warranty_on(context.site(), day)
    emit_rows(
        context,
        [
            Column("tag"),
            Column("model"),
            Column("fitted"),
            Column("warranty ends"),
            Column.number("days left"),
        ],
        [
            (
                str(fitting.tag),
                f"{fitting.manufacturer} {fitting.model_code}",
                fitting.fitted_on.isoformat(),
                fitting.warranty_ends.isoformat(),
                (fitting.warranty_ends - day).days,
            )
            for fitting in fittings
        ],
        keys=["tag", "model", "fitted", "warranty_ends", "days_left"],
        empty="nothing on this site is still under warranty",
    )


@trap_group.command("sizing")
@click.option("--wrong-only", is_flag=True, help="Only the stations that are not right.")
@click.option(
    "--cold-f", default=60.0, show_default=True, type=float, help="Temperature the run starts from."
)
@click.pass_obj
def trap_sizing(context: Context, wrong_only: bool, cold_f: float) -> None:
    """Hold every drip station against the condensate it has to clear."""

    audit = audit_sizing(register_for(context), cold=Temperature.from_fahrenheit(cold_f))
    rows = audit.wrong if wrong_only else audit.rows
    emit_rows(
        context,
        [
            Column("tag"),
            Column("pipe"),
            Column.number("run ft"),
            Column.number("warm up"),
            Column.number("running"),
            Column.number("capacity"),
            Column.number("ratio"),
            Column("verdict"),
        ],
        [
            (
                str(row.tag),
                row.station.pipe_nominal or "",
                f"{row.station.run_length_ft:,.0f}" if row.station.run_length_ft else "",
                f"{row.warmup_pph:,.0f}",
                f"{row.running_pph:,.1f}",
                f"{row.check.capacity.pounds_per_hour:,.0f}",
                f"{row.check.ratio:.1f}",
                row.verdict.label,
            )
            for row in rows
        ],
        keys=[
            "tag",
            "pipe",
            "run_ft",
            "warmup_pph",
            "running_pph",
            "capacity_pph",
            "ratio",
            "verdict",
        ],
        empty="nothing on this register can be sized",
    )


@trap_group.command("import")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--dry-run", is_flag=True, help="Read the file and report, write nothing.")
@click.option(
    "--quarantine",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write the rows that would not read to this file.",
)
@click.pass_obj
def trap_import(context: Context, path: Path, dry_run: bool, quarantine: Path | None) -> None:
    """Read an asset register export into the book."""

    plant = PlantRepository(context.book)
    result = read_register_csv(
        path.read_text(encoding="utf-8"),
        context.site(),
        plant.list_headers(context.site()),
        CatalogueRepository(context.book).load_catalogue(),
        ProfileRepository(context.book).list_for(context.site()),
    )
    repo = StationRepository(context.book)
    if not dry_run:
        repo.save_many(result.stations)
    if quarantine is not None and result.quarantined:
        write_quarantine(result.quarantined, quarantine)
    emit_facts(
        context,
        {
            "file": str(path),
            "content_hash": result.content_hash,
            "read": result.read,
            "quarantined": result.rejected,
            "written": 0 if dry_run else result.read,
            "dry_run": dry_run,
            "quarantine_file": "" if quarantine is None else str(quarantine),
            "quarantine": [str(row) for row in result.quarantined],
        },
    )


@trap_group.command("export")
@click.option("--live", is_flag=True, help="Only traps still in service today.")
@click.pass_obj
def trap_export(context: Context, live: bool) -> None:
    """Write the register out in the shape `trap import` reads back."""

    register = StationRepository(context.book).load_register(context.site())
    stations = register.in_service_on(dt.date.today()) if live else list(register)
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(EXPORT_COLUMNS)
    for station in stations:
        writer.writerow(
            [
                str(station.tag),
                station.model.manufacturer,
                station.model.code,
                station.installed_on.isoformat(),
                station.service.value,
                station.accessibility.value,
                station.criticality.value,
                station.profile.code,
                "" if station.destination is None else station.destination.value,
                "y" if station.strainer_fitted else "n",
                station.isolation_valves,
                station.interval_months_override or "",
                station.note,
            ]
        )


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
