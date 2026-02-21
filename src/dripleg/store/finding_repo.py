"""Findings and work orders, in and out of the book.

A finding is a flattened loss register row: the verdict, the numbers it
produced, and the rules that got there. It is stored rather than recomputed
because the prices, the emissions factor and the rule set all move, and a
report reissued next year has to show what was actually said at the time.

The evidence itself is not stored as objects. The rule codes are, which is
enough to reproduce the reasoning against the build that produced it, and a
great deal less than serialising a rule engine's internals into a database
column where nothing can migrate it.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass

from dripleg.errors import NotFoundError
from dripleg.loss.register import LossRegister
from dripleg.model.tags import SiteCode, TrapTag
from dripleg.repair.recommend import Action
from dripleg.repair.workorder import WorkOrder, WorkOrderState
from dripleg.store.codes import enum_from_value
from dripleg.store.db import Database
from dripleg.survey.condition import TrapCondition
from dripleg.units.money import Money

__all__ = ["FindingRepository", "StoredFinding", "WorkOrderRepository"]


def _site(site: SiteCode | str) -> SiteCode:
    return site if isinstance(site, SiteCode) else SiteCode.parse(site)


def _date(value: object) -> dt.date | None:
    return None if value is None else dt.date.fromisoformat(str(value))


@dataclass(frozen=True)
class StoredFinding:
    """One row of a loss register as it came back out of the book."""

    tag: TrapTag
    survey_reference: str
    diagnosed: TrapCondition
    reported: TrapCondition
    confidence: float
    flags: tuple[str, ...]
    rules_fired: tuple[str, ...]
    pounds_per_hour: float
    pounds_per_year: float
    fuel_mmbtu_per_year: float
    tonnes_co2e: float
    annual_cost: Money

    @property
    def agreed_with_technician(self) -> bool:
        return self.diagnosed is self.reported

    @property
    def is_losing(self) -> bool:
        return self.pounds_per_hour > 0

    def __str__(self) -> str:
        return f"{self.tag} {self.diagnosed.label} {self.annual_cost} a year"


class FindingRepository:
    """The costed verdicts from a survey."""

    def __init__(self, book: Database) -> None:
        self.book = book

    def save_register(self, site: SiteCode | str, register: LossRegister) -> int:
        site_code = _site(site)
        with self.book.transaction():
            self.book.execute(
                "DELETE FROM finding WHERE site_code = ? AND survey_reference = ?",
                (site_code.value, register.reference),
            )
            for row in register.rows:
                self.book.execute(
                    "INSERT INTO finding (site_code, survey_reference, tag, diagnosed, "
                    "reported, confidence, flags, rules_fired, pounds_per_hour, "
                    "pounds_per_year, fuel_mmbtu_per_year, tonnes_co2e, annual_cost_cents) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        site_code.value,
                        register.reference,
                        str(row.tag),
                        row.diagnosis.condition.value,
                        row.diagnosis.reported_condition.value,
                        row.diagnosis.confidence,
                        "|".join(row.diagnosis.flags),
                        "|".join(row.diagnosis.evidence.rules_fired),
                        row.steam.flow.pounds_per_hour,
                        row.steam.pounds_per_year,
                        row.heat.mmbtu_per_year,
                        row.stack.tonnes_co2e,
                        row.annual_cost.cents,
                    ),
                )
        return len(register.rows)

    def for_survey(self, site: SiteCode | str, reference: str) -> list[StoredFinding]:
        rows = self.book.query(
            "SELECT * FROM finding WHERE site_code = ? AND survey_reference = ? ORDER BY tag",
            (_site(site).value, reference.strip().upper()),
        )
        return [self._from(row) for row in rows]

    def dearest(self, site: SiteCode | str, limit: int = 10) -> list[StoredFinding]:
        rows = self.book.query(
            "SELECT * FROM finding WHERE site_code = ? AND annual_cost_cents > 0 "
            "ORDER BY annual_cost_cents DESC, tag LIMIT ?",
            (_site(site).value, limit),
        )
        return [self._from(row) for row in rows]

    def history_for(self, site: SiteCode | str, tag: TrapTag | str) -> list[StoredFinding]:
        wanted = tag if isinstance(tag, TrapTag) else TrapTag.parse(tag)
        rows = self.book.query(
            "SELECT f.* FROM finding f JOIN survey s "
            "ON s.site_code = f.site_code AND s.reference = f.survey_reference "
            "WHERE f.site_code = ? AND f.tag = ? ORDER BY s.started_on",
            (_site(site).value, str(wanted)),
        )
        return [self._from(row) for row in rows]

    def last_verdict_per_trap(
        self, site: SiteCode | str
    ) -> dict[TrapTag, tuple[dt.date, TrapCondition]]:
        """The most recent verdict on every trap, keyed by tag.

        Recency is the survey's start date rather than the row order, because
        surveys get imported out of order and a book that decides what is
        current from insertion order is a book that reschedules the wrong trap.
        """

        rows = self.book.query(
            "SELECT f.tag, f.diagnosed, s.started_on FROM finding f JOIN survey s "
            "ON s.site_code = f.site_code AND s.reference = f.survey_reference "
            "WHERE f.site_code = ? ORDER BY s.started_on",
            (_site(site).value,),
        )
        latest: dict[TrapTag, tuple[dt.date, TrapCondition]] = {}
        for row in rows:
            tag = TrapTag.parse(str(row["tag"]))
            latest[tag] = (
                dt.date.fromisoformat(str(row["started_on"])),
                enum_from_value(TrapCondition, str(row["diagnosed"]), field="diagnosed"),
            )
        return latest

    def latest_finding_per_trap(
        self, site: SiteCode | str
    ) -> dict[TrapTag, tuple[dt.date, StoredFinding]]:
        """The most recent whole finding on every trap, with its survey date."""

        rows = self.book.query(
            "SELECT f.*, s.started_on FROM finding f JOIN survey s "
            "ON s.site_code = f.site_code AND s.reference = f.survey_reference "
            "WHERE f.site_code = ? ORDER BY s.started_on",
            (_site(site).value,),
        )
        latest: dict[TrapTag, tuple[dt.date, StoredFinding]] = {}
        for row in rows:
            finding = self._from(row)
            latest[finding.tag] = (dt.date.fromisoformat(str(row["started_on"])), finding)
        return latest

    def all_verdicts_per_trap(self, site: SiteCode | str) -> dict[TrapTag, list[TrapCondition]]:
        """Every verdict on every trap, oldest first, for the reliability cuts."""

        rows = self.book.query(
            "SELECT f.tag, f.diagnosed FROM finding f JOIN survey s "
            "ON s.site_code = f.site_code AND s.reference = f.survey_reference "
            "WHERE f.site_code = ? ORDER BY s.started_on",
            (_site(site).value,),
        )
        history: dict[TrapTag, list[TrapCondition]] = {}
        for row in rows:
            tag = TrapTag.parse(str(row["tag"]))
            history.setdefault(tag, []).append(
                enum_from_value(TrapCondition, str(row["diagnosed"]), field="diagnosed")
            )
        return history

    def total_cost(self, site: SiteCode | str, reference: str) -> Money:
        cents = self.book.scalar(
            "SELECT COALESCE(SUM(annual_cost_cents), 0) FROM finding "
            "WHERE site_code = ? AND survey_reference = ?",
            (_site(site).value, reference.strip().upper()),
        )
        return Money.from_cents(int(cents or 0))

    @staticmethod
    def _from(row: sqlite3.Row) -> StoredFinding:
        flags = str(row["flags"])
        rules = str(row["rules_fired"])
        return StoredFinding(
            tag=TrapTag.parse(str(row["tag"])),
            survey_reference=str(row["survey_reference"]),
            diagnosed=enum_from_value(TrapCondition, str(row["diagnosed"]), field="diagnosed"),
            reported=enum_from_value(TrapCondition, str(row["reported"]), field="reported"),
            confidence=float(row["confidence"]),
            flags=tuple(f for f in flags.split("|") if f),
            rules_fired=tuple(r for r in rules.split("|") if r),
            pounds_per_hour=float(row["pounds_per_hour"]),
            pounds_per_year=float(row["pounds_per_year"]),
            fuel_mmbtu_per_year=float(row["fuel_mmbtu_per_year"]),
            tonnes_co2e=float(row["tonnes_co2e"]),
            annual_cost=Money.from_cents(int(row["annual_cost_cents"])),
        )


class WorkOrderRepository:
    """Work orders and the trail of what happened to them."""

    def __init__(self, book: Database) -> None:
        self.book = book

    def save(self, site: SiteCode | str, order: WorkOrder) -> None:
        site_code = _site(site)
        with self.book.transaction():
            self.book.execute(
                "INSERT INTO work_order (number, site_code, tag, action, state, raised_on, "
                "due_on, assigned_to, started_on, completed_on, verified_on, "
                "estimated_cost_cents, actual_cost_cents) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(number) DO UPDATE SET state = excluded.state, "
                "due_on = excluded.due_on, assigned_to = excluded.assigned_to, "
                "started_on = excluded.started_on, completed_on = excluded.completed_on, "
                "verified_on = excluded.verified_on, "
                "actual_cost_cents = excluded.actual_cost_cents",
                (
                    order.number,
                    site_code.value,
                    str(order.tag),
                    order.action.value,
                    order.state.value,
                    order.raised_on.isoformat(),
                    order.due_on.isoformat(),
                    order.assigned_to,
                    None if order.started_on is None else order.started_on.isoformat(),
                    None if order.completed_on is None else order.completed_on.isoformat(),
                    None if order.verified_on is None else order.verified_on.isoformat(),
                    order.estimated_cost.cents,
                    None if order.actual_cost is None else order.actual_cost.cents,
                ),
            )
            self.book.execute("DELETE FROM work_order_event WHERE number = ?", (order.number,))
            self.book.execute_many(
                "INSERT INTO work_order_event (number, position, note) VALUES (?, ?, ?)",
                [(order.number, position, note) for position, note in enumerate(order.history)],
            )

    def get(self, number: str) -> WorkOrder:
        wanted = number.strip().upper()
        row = self.book.one("SELECT * FROM work_order WHERE number = ?", (wanted,))
        if row is None:
            raise NotFoundError("work order", wanted)
        events = self.book.query(
            "SELECT note FROM work_order_event WHERE number = ? ORDER BY position", (wanted,)
        )
        return WorkOrder(
            number=str(row["number"]),
            tag=TrapTag.parse(str(row["tag"])),
            action=enum_from_value(Action, str(row["action"]), field="action"),
            raised_on=dt.date.fromisoformat(str(row["raised_on"])),
            due_on=dt.date.fromisoformat(str(row["due_on"])),
            estimated_cost=Money.from_cents(int(row["estimated_cost_cents"])),
            state=enum_from_value(WorkOrderState, str(row["state"]), field="state"),
            assigned_to=None if row["assigned_to"] is None else str(row["assigned_to"]),
            started_on=_date(row["started_on"]),
            completed_on=_date(row["completed_on"]),
            verified_on=_date(row["verified_on"]),
            actual_cost=None
            if row["actual_cost_cents"] is None
            else Money.from_cents(int(row["actual_cost_cents"])),
            history=[str(event["note"]) for event in events],
        )

    def open_orders(self, site: SiteCode | str) -> list[WorkOrder]:
        rows = self.book.query(
            "SELECT number FROM work_order WHERE site_code = ? "
            "AND state NOT IN ('verified', 'cancelled') ORDER BY due_on, number",
            (_site(site).value,),
        )
        return [self.get(str(row["number"])) for row in rows]

    def overdue_on(self, site: SiteCode | str, day: dt.date) -> list[WorkOrder]:
        return [order for order in self.open_orders(site) if order.is_overdue_on(day)]

    def awaiting_verification(self, site: SiteCode | str) -> list[WorkOrder]:
        return [order for order in self.open_orders(site) if order.awaiting_verification]

    def for_tag(self, site: SiteCode | str, tag: TrapTag | str) -> list[WorkOrder]:
        wanted = tag if isinstance(tag, TrapTag) else TrapTag.parse(tag)
        rows = self.book.query(
            "SELECT number FROM work_order WHERE site_code = ? AND tag = ? ORDER BY raised_on",
            (_site(site).value, str(wanted)),
        )
        return [self.get(str(row["number"])) for row in rows]

    def next_number(self, site: SiteCode | str, prefix: str = "WO") -> str:
        count = self.book.scalar(
            "SELECT COUNT(*) FROM work_order WHERE site_code = ?", (_site(site).value,)
        )
        return f"{prefix.strip().upper()}-{int(count or 0) + 1:05d}"
