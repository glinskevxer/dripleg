"""`dripleg rules`: what the diagnosis engine is running at this site."""

from __future__ import annotations

import datetime as dt

import click

from dripleg.cli.context import Context
from dripleg.cli.loading import engine_for
from dripleg.cli.output import emit_facts, emit_rows
from dripleg.diagnosis.engine import DEFAULT_RULES
from dripleg.report.table import Column
from dripleg.store.rules_repo import RuleExclusion, RulesRepository

__all__ = ["rules_group"]


@click.group("rules")
def rules_group() -> None:
    """The diagnosis rules, and the ones this site has switched off."""


@rules_group.command("list")
@click.option("--off-only", is_flag=True, help="Only the rules that are switched off.")
@click.pass_obj
def rules_list(context: Context, off_only: bool) -> None:
    """Every rule in the build, and whether this site runs it."""

    repo = RulesRepository(context.book)
    off = {exclusion.rule_code: exclusion for exclusion in repo.exclusions(context.site())}
    rows = []
    for rule in DEFAULT_RULES:
        exclusion = off.get(rule.code)
        if off_only and exclusion is None:
            continue
        rows.append(
            (
                rule.code,
                rule.method.value,
                rule.description,
                "off" if exclusion is not None else "on",
                "" if exclusion is None else exclusion.reason,
            )
        )
    emit_rows(
        context,
        [
            Column("rule"),
            Column("method"),
            Column("what it looks for", max_width=60),
            Column("state"),
            Column("reason", max_width=40),
        ],
        rows,
        keys=["rule", "method", "description", "state", "reason"],
        empty="every rule is on at this site",
    )


@rules_group.command("off")
@click.argument("rule")
@click.option("--reason", required=True, help="Why this site does not run it.")
@click.option("--on", default=None, help="The day it was switched off.")
@click.pass_obj
def rules_off(context: Context, rule: str, reason: str, on: str | None) -> None:
    """Switch a rule off at this site, with a reason on the record."""

    repo = RulesRepository(context.book)
    repo.exclude(
        context.site(),
        RuleExclusion(
            rule_code=rule,
            reason=reason,
            excluded_on=dt.date.fromisoformat(on) if on is not None else dt.date.today(),
        ),
    )
    emit_facts(
        context,
        {
            "rule": rule.strip().upper(),
            "state": "off",
            "reason": reason,
            "rules_running": len(engine_for(context).rules),
        },
    )


@rules_group.command("on")
@click.argument("rule")
@click.pass_obj
def rules_on(context: Context, rule: str) -> None:
    """Switch a rule back on."""

    was_off = RulesRepository(context.book).include(context.site(), rule)
    emit_facts(
        context,
        {
            "rule": rule.strip().upper(),
            "state": "on",
            "was_off": was_off,
            "rules_running": len(engine_for(context).rules),
        },
    )


@rules_group.command("stale")
@click.pass_obj
def rules_stale(context: Context) -> None:
    """Exclusions naming rules this build does not have any more."""

    stale = RulesRepository(context.book).stale_exclusions(context.site())
    emit_rows(
        context,
        [Column("rule"), Column("switched off"), Column("reason", max_width=50)],
        [(e.rule_code, e.excluded_on.isoformat(), e.reason) for e in stale],
        keys=["rule", "excluded_on", "reason"],
        empty="every exclusion names a rule this build has",
    )
