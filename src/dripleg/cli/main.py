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


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
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


@cli.command()
@click.pass_obj
def about(context: Context) -> None:
    """Say what this build is and what the book holds."""

    facts = {
        "version": __version__,
        "book": context.book_path,
        "schema_version": context.version_of_book,
        "latest_migration": MIGRATIONS[-1].number,
        "sites": int(context.book.scalar("SELECT COUNT(*) FROM site") or 0),
        "trap_models": int(context.book.scalar("SELECT COUNT(*) FROM trap_model") or 0),
        "trap_stations": int(context.book.scalar("SELECT COUNT(*) FROM trap_station") or 0),
    }
    if context.as_json:
        click.echo(json.dumps(facts, indent=2))
        return
    width = max(len(k) for k in facts)
    for key, value in facts.items():
        click.echo(f"{key.replace('_', ' '):<{width}}  {value}")


cli.add_command(book_group)
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
    """The console entry point, which turns our errors into exit codes."""

    try:
        cli.main(standalone_mode=False)
    except click.ClickException as problem:
        problem.show()
        return problem.exit_code
    except click.Abort:
        click.echo("aborted", err=True)
        return 130
    except DriplegError as problem:
        click.echo(f"error: {problem}", err=True)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(run())
