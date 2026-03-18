"""Findings the plant has decided to live with, and when it will look again.

Every survey produces a handful of traps that are not going to be fixed. The
line comes out in six weeks, the trap is on a vessel that only runs at
Christmas, the money is not there this year. Those decisions are legitimate and
they get made whether or not the software has a place to put them.

What matters is that the decision is written down rather than expressed by the
trap staying on the list and being ignored, because a list with eleven
permanent residents on it stops being read. So an acceptance carries who made
it, why, and a review date, and it expires: past the review date the finding
comes back onto the work list on its own.

An acceptance is never a way to make a loss disappear. The trap still costs
what it costs and it still appears in the loss register. It only comes off the
work list, which is a different question.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from dripleg.errors import NotFoundError, ValidationError
from dripleg.model.tags import SiteCode, TrapTag
from dripleg.store.db import Database
from dripleg.store.keys import as_date, as_site, as_tag

__all__ = ["AcceptedRisk", "RiskRepository"]

DEFAULT_REVIEW_MONTHS = 12


@dataclass(frozen=True)
class AcceptedRisk:
    """One trap the plant has decided not to fix, for now."""

    tag: TrapTag
    reason: str
    accepted_by: str
    accepted_on: dt.date
    review_on: dt.date

    def __post_init__(self) -> None:
        reason = " ".join(self.reason.split())
        if not reason:
            raise ValidationError("an acceptance has to say why", field="reason")
        object.__setattr__(self, "reason", reason)
        who = " ".join(self.accepted_by.split())
        if not who:
            raise ValidationError("an acceptance has to say who made it", field="accepted_by")
        object.__setattr__(self, "accepted_by", who)
        if self.review_on <= self.accepted_on:
            raise ValidationError("an acceptance is reviewed later", field="review_on")

    def is_live_on(self, day: dt.date) -> bool:
        return self.accepted_on <= day < self.review_on

    def days_left_on(self, day: dt.date) -> int:
        return max((self.review_on - day).days, 0)

    def __str__(self) -> str:
        return (
            f"{self.tag} accepted by {self.accepted_by} on {self.accepted_on}, "
            f"back on the list {self.review_on}"
        )


class RiskRepository:
    """The acceptances one site carries."""

    def __init__(self, book: Database) -> None:
        self.book = book

    def accept(self, site: SiteCode | str, risk: AcceptedRisk) -> None:
        site_code = as_site(site)
        exists = self.book.scalar(
            "SELECT COUNT(*) FROM trap_station WHERE site_code = ? AND tag = ?",
            (site_code.value, str(risk.tag)),
        )
        if not exists:
            raise NotFoundError("trap station", str(risk.tag))
        with self.book.transaction():
            self.book.execute(
                "INSERT INTO accepted_risk (site_code, tag, reason, accepted_by, "
                "accepted_on, review_on) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(site_code, tag) DO UPDATE SET reason = excluded.reason, "
                "accepted_by = excluded.accepted_by, accepted_on = excluded.accepted_on, "
                "review_on = excluded.review_on",
                (
                    site_code.value,
                    str(risk.tag),
                    risk.reason,
                    risk.accepted_by,
                    risk.accepted_on.isoformat(),
                    risk.review_on.isoformat(),
                ),
            )

    def withdraw(self, site: SiteCode | str, tag: TrapTag | str) -> bool:
        site_code = as_site(site)
        wanted = as_tag(tag)
        before = self.book.scalar(
            "SELECT COUNT(*) FROM accepted_risk WHERE site_code = ? AND tag = ?",
            (site_code.value, str(wanted)),
        )
        with self.book.transaction():
            self.book.execute(
                "DELETE FROM accepted_risk WHERE site_code = ? AND tag = ?",
                (site_code.value, str(wanted)),
            )
        return bool(before)

    def all_for(self, site: SiteCode | str) -> list[AcceptedRisk]:
        rows = self.book.query(
            "SELECT * FROM accepted_risk WHERE site_code = ? ORDER BY review_on, tag",
            (as_site(site).value,),
        )
        return [
            AcceptedRisk(
                tag=TrapTag.parse(str(row["tag"])),
                reason=str(row["reason"]),
                accepted_by=str(row["accepted_by"]),
                accepted_on=as_date(row["accepted_on"]),
                review_on=as_date(row["review_on"]),
            )
            for row in rows
        ]

    def live_on(self, site: SiteCode | str, day: dt.date) -> dict[TrapTag, AcceptedRisk]:
        """The acceptances still in force on a day, keyed by tag."""

        return {risk.tag: risk for risk in self.all_for(site) if risk.is_live_on(day)}

    def due_for_review(self, site: SiteCode | str, day: dt.date) -> list[AcceptedRisk]:
        return [risk for risk in self.all_for(site) if not risk.is_live_on(day)]
