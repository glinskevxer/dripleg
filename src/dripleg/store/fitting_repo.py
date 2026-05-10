"""What was fitted to a station and when, which the station itself cannot say.

A station carries the trap that is in it now. That is the right thing for a
station to carry and it loses the history: change a trap three times and the
first two are gone, along with any chance of asking how long they lasted or
whether the last one failed inside its warranty.

So a fitting is written every time a trap goes in, and it is written from the
work order that put it there where there is one. The station stays as it is,
the history sits beside it, and neither has to know much about the other.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from dripleg.errors import ConflictError, ValidationError
from dripleg.model.calendar import add_months
from dripleg.model.catalogue import TrapModel
from dripleg.model.tags import SiteCode, TrapTag
from dripleg.store.db import Database
from dripleg.store.keys import as_date, as_site, as_tag

__all__ = ["Fitting", "FittingRepository"]


@dataclass(frozen=True)
class Fitting:
    """One trap going into one station on one day."""

    tag: TrapTag
    fitted_on: dt.date
    manufacturer: str
    model_code: str
    warranty_months: int = 12
    work_order: str | None = None

    def __post_init__(self) -> None:
        if not self.manufacturer.strip() or not self.model_code.strip():
            raise ValidationError("a fitting names a model", field="model_code")
        if self.warranty_months < 0:
            raise ValidationError("a warranty is not negative", field="warranty_months")

    @property
    def warranty_ends(self) -> dt.date:
        return add_months(self.fitted_on, self.warranty_months)

    def is_in_warranty_on(self, day: dt.date) -> bool:
        return self.fitted_on <= day < self.warranty_ends

    def age_days_on(self, day: dt.date) -> int:
        return max((day - self.fitted_on).days, 0)

    def __str__(self) -> str:
        return f"{self.manufacturer} {self.model_code} fitted to {self.tag} on {self.fitted_on}"


class FittingRepository:
    """The trap that went into each station, every time."""

    def __init__(self, book: Database) -> None:
        self.book = book

    def record(
        self,
        site: SiteCode | str,
        tag: TrapTag | str,
        model: TrapModel,
        fitted_on: dt.date,
        work_order: str | None = None,
    ) -> Fitting:
        site_code = as_site(site)
        wanted = as_tag(tag)
        exists = self.book.scalar(
            "SELECT COUNT(*) FROM trap_station WHERE site_code = ? AND tag = ?",
            (site_code.value, str(wanted)),
        )
        if not exists:
            raise ConflictError(f"{wanted} is not a station at {site_code}")
        with self.book.transaction():
            self.book.execute(
                "INSERT INTO trap_fitting (site_code, tag, fitted_on, manufacturer, "
                "model_code, work_order) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(site_code, tag, fitted_on) DO UPDATE SET "
                "manufacturer = excluded.manufacturer, model_code = excluded.model_code, "
                "work_order = excluded.work_order",
                (
                    site_code.value,
                    str(wanted),
                    fitted_on.isoformat(),
                    model.manufacturer,
                    model.code,
                    work_order,
                ),
            )
        return Fitting(
            tag=wanted,
            fitted_on=fitted_on,
            manufacturer=model.manufacturer,
            model_code=model.code,
            warranty_months=model.warranty_months,
            work_order=work_order,
        )

    def history_for(self, site: SiteCode | str, tag: TrapTag | str) -> list[Fitting]:
        rows = self.book.query(
            "SELECT f.*, m.warranty_months FROM trap_fitting f "
            "JOIN trap_model m ON m.manufacturer = f.manufacturer AND m.code = f.model_code "
            "WHERE f.site_code = ? AND f.tag = ? ORDER BY f.fitted_on",
            (as_site(site).value, str(as_tag(tag))),
        )
        return [self._from(row) for row in rows]

    def all_for(self, site: SiteCode | str) -> list[Fitting]:
        rows = self.book.query(
            "SELECT f.*, m.warranty_months FROM trap_fitting f "
            "JOIN trap_model m ON m.manufacturer = f.manufacturer AND m.code = f.model_code "
            "WHERE f.site_code = ? ORDER BY f.fitted_on, f.tag",
            (as_site(site).value,),
        )
        return [self._from(row) for row in rows]

    def in_warranty_on(self, site: SiteCode | str, day: dt.date) -> list[Fitting]:
        """The newest fitting on each station, where it is still under warranty."""

        newest: dict[TrapTag, Fitting] = {}
        for fitting in self.all_for(site):
            newest[fitting.tag] = fitting
        return sorted(
            (f for f in newest.values() if f.is_in_warranty_on(day)),
            key=lambda f: (f.warranty_ends, str(f.tag)),
        )

    def service_lives(self, site: SiteCode | str) -> dict[TrapTag, list[int]]:
        """How many days each replaced trap lasted, per station."""

        lives: dict[TrapTag, list[int]] = {}
        by_tag: dict[TrapTag, list[Fitting]] = {}
        for fitting in self.all_for(site):
            by_tag.setdefault(fitting.tag, []).append(fitting)
        for tag, fittings in by_tag.items():
            spans = [
                (later.fitted_on - earlier.fitted_on).days
                for earlier, later in zip(fittings, fittings[1:], strict=False)
            ]
            if spans:
                lives[tag] = spans
        return lives

    @staticmethod
    def _from(row: object) -> Fitting:
        mapping = dict(row)  # type: ignore[call-overload]
        order = mapping["work_order"]
        return Fitting(
            tag=TrapTag.parse(str(mapping["tag"])),
            fitted_on=as_date(mapping["fitted_on"]),
            manufacturer=str(mapping["manufacturer"]),
            model_code=str(mapping["model_code"]),
            warranty_months=int(mapping["warranty_months"]),
            work_order=None if order is None else str(order),
        )
