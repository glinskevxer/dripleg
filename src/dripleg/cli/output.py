"""Printing a command's answer as text or as json, decided in one place.

Every command wants the same shape: a table for a person and a list of objects
for a script, and the two must not drift. So a command builds the rows once and
hands them here with the column headings, and this decides which way out.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import click

from dripleg.cli.context import Context
from dripleg.report.table import Column, Table

__all__ = [
    "emit_facts",
    "emit_lines",
    "emit_rows",
]


def emit_rows(
    context: Context,
    columns: Sequence[Column],
    rows: Sequence[Sequence[object]],
    *,
    keys: Sequence[str] | None = None,
    empty: str = "nothing to show",
) -> None:
    """A table of rows, or the same rows as a json list of objects."""

    if context.as_json:
        names = list(keys) if keys is not None else [c.heading for c in columns]
        click.echo(
            json.dumps(
                [dict(zip(names, [str(v) for v in row], strict=False)) for row in rows], indent=2
            )
        )
        return
    if not rows:
        click.echo(empty)
        return
    table = Table(columns)
    table.extend(rows)
    click.echo(table.render())


def emit_facts(context: Context, facts: dict[str, object]) -> None:
    """A block of name and value pairs."""

    if context.as_json:
        click.echo(json.dumps(facts, indent=2, default=str))
        return
    if not facts:
        click.echo("nothing to show")
        return
    width = max(len(key) for key in facts)
    for key, value in facts.items():
        click.echo(f"{key.replace('_', ' '):<{width}}  {value}")


def emit_lines(context: Context, lines: Sequence[str], payload: object) -> None:
    """A rendered report, or its json shape."""

    if context.as_json:
        click.echo(json.dumps(payload, indent=2, default=str))
        return
    for line in lines:
        click.echo(line)
