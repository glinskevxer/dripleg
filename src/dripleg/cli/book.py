"""`dripleg book`: looking after the file itself."""

from __future__ import annotations

import click

from dripleg.cli.context import Context
from dripleg.cli.output import emit_facts, emit_rows
from dripleg.report.table import Column
from dripleg.store.audit import audit_book
from dripleg.store.migrations import MIGRATIONS, applied_migrations, schema_version
from dripleg.tools.check_migrations import schema_fingerprint

__all__ = ["book_group"]


@click.group("book")
def book_group() -> None:
    """The sqlite file: its state, its integrity and its consistency."""


@book_group.command("check")
@click.pass_obj
def book_check(context: Context) -> None:
    """Run sqlite's own integrity check and report the schema state."""

    context.book.integrity_check()
    applied = applied_migrations(context.book)
    emit_facts(
        context,
        {
            "path": context.book_path,
            "integrity": "ok",
            "schema_version": schema_version(context.book),
            "latest_migration": MIGRATIONS[-1].number,
            "migrations_applied": len(applied),
            "up_to_date": schema_version(context.book) == MIGRATIONS[-1].number,
            "fingerprint": schema_fingerprint(context.book)[:12],
            "tables": len(context.book.table_names()),
        },
    )


@book_group.command("audit")
@click.pass_obj
def book_audit(context: Context) -> None:
    """Look for the inconsistencies foreign keys cannot catch."""

    audit = audit_book(context.book, context.site())
    emit_rows(
        context,
        [Column("finding"), Column("detail", max_width=70)],
        [(finding.kind, finding.detail) for finding in audit.findings],
        keys=["kind", "detail"],
        empty="nothing wrong with this book",
    )


@book_group.command("vacuum")
@click.pass_obj
def book_vacuum(context: Context) -> None:
    """Rebuild the file, which reclaims space after a big delete."""

    before = context.book.scalar("PRAGMA page_count") or 0
    context.book.execute("VACUUM")
    after = context.book.scalar("PRAGMA page_count") or 0
    page = context.book.scalar("PRAGMA page_size") or 0
    emit_facts(
        context,
        {
            "path": context.book_path,
            "pages_before": int(before),
            "pages_after": int(after),
            "bytes_saved": int((int(before) - int(after)) * int(page)),
        },
    )
