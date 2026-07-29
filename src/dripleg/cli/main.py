"""The `dripleg` command."""

from __future__ import annotations

import json
import sys

import click

from dripleg import __version__
from dripleg.cli.book import book_group
from dripleg.cli.catalogue import model_group, profile_group
from dripleg.cli.context import DEFAULT_BOOK, Context
from dripleg.cli.costing import loss_group, prices_group
from dripleg.cli.doctor import doctor_command
from dripleg.cli.fleet import fleet_group
from dripleg.cli.plant import area_group, header_group, site_group
from dripleg.cli.programme import programme_group
from dripleg.cli.risk import risk_group
from dripleg.cli.routes import route_group
from dripleg.cli.rules import rules_group
from dripleg.cli.surveys import survey_group
from dripleg.cli.traps import trap_group
from dripleg.cli.work import work_group
from dripleg.errors import DriplegError
from dripleg.store.migrations import MIGRATIONS

__all__ = ["cli", "run"]


class DriplegGroup(click.Group):
    """The top level group, with our own errors turned into clean messages.

    Without this a `NotFoundError` reaches click as an unhandled exception and
    the user gets a traceback for the ordinary case of naming a survey that is
    not there. Click's own `UsageError` machinery is the right shape for it, so
    our errors are translated into that rather than printed by hand: the exit
    code, the stream and the formatting then all match what click does for
    everything else.
    """

    def invoke(self, ctx: click.Context) -> object:
        try:
            return super().invoke(ctx)
        except DriplegError as problem:
            raise click.ClickException(str(problem)) from problem


@click.group(cls=DriplegGroup, context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--book",
    "book_path",
    default=DEFAULT_BOOK,
    show_default=True,
    envvar="DRIPLEG_BOOK",
    help="The sqlite file to work on.",
)
@click.option("--site", "site_code", default=None, envvar="DRIPLEG_SITE", help="Site code.")
@click.option("--json", "as_json", is_flag=True, help="Print machine readable output.")
@click.version_option(__version__, prog_name="dripleg")
@click.pass_context
def cli(ctx: click.Context, book_path: str, site_code: str | None, as_json: bool) -> None:
    """Steam trap survey register and steam loss accounting."""

    ctx.obj = Context(book_path=book_path, site_code=site_code, as_json=as_json)
    ctx.call_on_close(ctx.obj.close)


@cli.command()
@click.pass_obj
def init(context: Context) -> None:
    """Make the book if it is not there, and apply anything outstanding."""

    applied = context.create_book()
    if context.as_json:
        click.echo(json.dumps({"book": context.book_path, "applied": applied}, indent=2))
        return
    if not applied:
        click.echo(
            f"{context.book_path} is already up to date at version {context.version_of_book}"
        )
        return
    for line in applied:
        click.echo(f"applied {line}")


def _count(context: Context, table: str, where: str = "", *parameters: object) -> int:
    clause = f" WHERE {where}" if where else ""
    return int(context.book.scalar(f"SELECT COUNT(*) FROM {table}{clause}", parameters) or 0)


@cli.command()
@click.option("--full", is_flag=True, help="Count everything, not just the headline.")
@click.pass_obj
def about(context: Context, full: bool) -> None:
    """Say what this build is and what the book holds."""

    facts: dict[str, object] = {
        "version": __version__,
        "book": context.book_path,
        "schema_version": context.version_of_book,
        "latest_migration": MIGRATIONS[-1].number,
        "up_to_date": context.version_of_book == MIGRATIONS[-1].number,
        "sites": _count(context, "site"),
        "trap_models": _count(context, "trap_model"),
        "trap_stations": _count(context, "trap_station"),
    }
    if full:
        facts.update(
            {
                "areas": _count(context, "area"),
                "headers": _count(context, "header"),
                "routes": _count(context, "route"),
                "surveys": _count(context, "survey"),
                "readings": _count(context, "observation"),
                "costed_findings": _count(context, "finding"),
                "work_orders": _count(context, "work_order"),
                "open_work_orders": _count(
                    context, "work_order", "state NOT IN ('verified', 'cancelled')"
                ),
                "accepted_risks": _count(context, "accepted_risk"),
                "rules_switched_off": _count(context, "rule_exclusion"),
                "fittings_recorded": _count(context, "trap_fitting"),
                "site_codes": ", ".join(context.site_codes()),
            }
        )
    if context.as_json:
        click.echo(json.dumps(facts, indent=2))
        return
    width = max(len(k) for k in facts)
    for key, value in facts.items():
        click.echo(f"{key.replace('_', ' '):<{width}}  {value}")


cli.add_command(book_group)
cli.add_command(doctor_command)
cli.add_command(fleet_group)
cli.add_command(site_group)
cli.add_command(area_group)
cli.add_command(header_group)
cli.add_command(model_group)
cli.add_command(profile_group)
cli.add_command(prices_group)
cli.add_command(loss_group)
cli.add_command(programme_group)
cli.add_command(risk_group)
cli.add_command(route_group)
cli.add_command(rules_group)
cli.add_command(survey_group)
cli.add_command(trap_group)
cli.add_command(work_group)


def run() -> int:
    """The console entry point, which turns our errors into exit codes.

    `SystemExit` comes through here too, because a command that decides its own
    exit code raises one and click would otherwise let it past unread.
    """

    try:
        cli.main(standalone_mode=False)
    except click.ClickException as problem:
        problem.show()
        return problem.exit_code
    except click.Abort:
        click.echo("aborted", err=True)
        return 130
    except SystemExit as stopping:
        return int(stopping.code or 0)
    except DriplegError as problem:
        click.echo(f"error: {problem}", err=True)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(run())
