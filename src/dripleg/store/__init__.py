"""Persistence: one sqlite file per site, opened through one class."""

from __future__ import annotations

from dripleg.store.db import Database, open_book

__all__ = ["Database", "open_book"]
