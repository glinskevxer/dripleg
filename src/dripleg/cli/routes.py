"""`dripleg route`: the walks, and the traps no walk visits."""

from __future__ import annotations

import click

from dripleg.cli.context import Context
from dripleg.cli.loading import register_for
from dripleg.cli.output import emit_facts, emit_rows
from dripleg.report.table import Column
from dripleg.store.survey_repo import RouteRepository
from dripleg.survey.route import Route, unrouted_tags

__all__ = ["route_group"]


@click.group("route")
def route_group() -> None:
    """Routes: the order a technician walks the traps in."""


@route_group.command("add")
@click.argument("code")
@click.argument("name")
@click.option(
    "--minutes-per-stop",
    default=6.0,
    show_default=True,
    type=float,
    help="How long one trap takes.",
)
@click.option(
    "--walk-minutes", default=30.0, show_default=True, type=float, help="Getting there and back."
)
@click.pass_obj
def route_add(
    context: Context, code: str, name: str, minutes_per_stop: float, walk_minutes: float
) -> None:
    """Add an empty route, or update the timings on one."""

    repo = RouteRepository(context.book)
    existing = None
    try:
        existing = repo.get(context.site(), code)
    except Exception:  # noqa: BLE001 - a missing route is the ordinary case here
        existing = None
    route = Route.of(context.site(), code, name)
    if existing is not None:
        route.stops = existing.stops
    route.minutes_per_stop = minutes_per_stop
    route.walk_minutes = walk_minutes
    repo.save(route)
    emit_facts(context, _facts(route))


@route_group.command("stop")
@click.argument("code")
@click.argument("tag")
@click.option("--after", default=None, help="Insert it after this tag.")
@click.option("--drop", is_flag=True, help="Take the stop off instead.")
@click.pass_obj
def route_stop(context: Context, code: str, tag: str, after: str | None, drop: bool) -> None:
    """Add or drop one stop, keeping the rest of the walk in order."""

    repo = RouteRepository(context.book)
    route = repo.get(context.site(), code)
    if drop:
        route.drop_stop(tag)
    else:
        route.add_stop(tag, after=after)
    repo.save(route)
    emit_facts(context, _facts(route))


@route_group.command("show")
@click.argument("code")
@click.pass_obj
def route_show(context: Context, code: str) -> None:
    """The walk, in order, with anything no longer on the register flagged."""

    route = RouteRepository(context.book).get(context.site(), code)
    register = register_for(context)
    rows: list[tuple[object, ...]] = []
    for position, tag in enumerate(route.stops):
        station = register.find(tag)
        rows.append(
            (
                position + 1,
                str(tag),
                "" if station is None else station.service.label,
                "no" if station is None else "yes",
            )
        )
    emit_rows(
        context,
        [Column.number("stop"), Column("tag"), Column("service"), Column("on the register")],
        rows,
        keys=["stop", "tag", "service", "registered"],
        empty="that route has no stops on it",
    )


@route_group.command("list")
@click.pass_obj
def route_list(context: Context) -> None:
    """Every route at a site."""

    routes = RouteRepository(context.book).list_for(context.site())
    emit_rows(
        context,
        [Column("code"), Column("name"), Column.number("stops"), Column.number("hours")],
        [(r.code, r.name, len(r), f"{r.estimated_hours:.1f}") for r in routes],
        keys=["code", "name", "stops", "hours"],
        empty="no routes yet",
    )


@route_group.command("coverage")
@click.pass_obj
def route_coverage(context: Context) -> None:
    """Traps on the register that no route visits."""

    register = register_for(context)
    routes = RouteRepository(context.book).list_for(context.site())
    missed = [register.get(tag) for tag in unrouted_tags(register, routes)]
    emit_rows(
        context,
        [Column("tag"), Column("service"), Column("criticality")],
        [(str(s.tag), s.service.label, s.criticality.value) for s in missed],
        keys=["tag", "service", "criticality"],
        empty="every trap is on a route",
    )


@route_group.command("split")
@click.argument("code")
@click.option(
    "--days", default=2, show_default=True, type=int, help="How many days to spread it over."
)
@click.pass_obj
def route_split(context: Context, code: str, days: int) -> None:
    """Cut a route into day sized pieces, keeping the order."""

    route = RouteRepository(context.book).get(context.site(), code)
    pieces = route.split(days)
    emit_rows(
        context,
        [Column.number("day"), Column.number("stops"), Column("from"), Column("to")],
        [
            (
                index + 1,
                len(piece),
                str(piece[0]) if piece else "",
                str(piece[-1]) if piece else "",
            )
            for index, piece in enumerate(pieces)
        ],
        keys=["day", "stops", "from", "to"],
        empty="that route has no stops on it",
    )


def _facts(route: Route) -> dict[str, object]:
    return {
        "code": route.code,
        "name": route.name,
        "stops": len(route),
        "areas": ", ".join(str(a) for a in route.areas),
        "minutes_per_stop": route.minutes_per_stop,
        "walk_minutes": route.walk_minutes,
        "estimated_hours": round(route.estimated_hours, 2),
    }
