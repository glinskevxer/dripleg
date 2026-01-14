"""Checking a book for the things foreign keys cannot catch.

Foreign keys stop an orphan row being written. They do not stop a book being
wrong in the ways this package actually gets books wrong, which are all about
tags, because a tag is a string in some tables and a key in others:

- a work order on a tag no station carries, from a station that was deleted
- a route stop pointing at a tag that is not on the register
- a reading on a trap that was out of service on the day it was read
- a survey with no readings on it at all, which is an import that failed
- a station whose model is rated below the header it hangs off, which the
  schema cannot see because pressure lives in two tables

None of these is fatal and every one of them makes a report wrong somewhere, so
they are collected as findings rather than raised, and the command prints them.
"""

from __future__ import annotations

from dataclasses import dataclass

from dripleg.model.tags import SiteCode
from dripleg.store.db import Database

__all__ = ["BookAudit", "BookFinding", "audit_book"]


@dataclass(frozen=True)
class BookFinding:
    """One thing wrong with a book."""

    kind: str
    detail: str

    def __str__(self) -> str:
        return f"{self.kind}: {self.detail}"


@dataclass(frozen=True)
class BookAudit:
    """Everything wrong with one site's book."""

    site: str
    findings: list[BookFinding]

    @property
    def is_clean(self) -> bool:
        return not self.findings

    def of_kind(self, kind: str) -> list[BookFinding]:
        return [finding for finding in self.findings if finding.kind == kind]

    def kinds(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.kind] = counts.get(finding.kind, 0) + 1
        return dict(sorted(counts.items()))

    def __str__(self) -> str:
        if self.is_clean:
            return f"{self.site}: nothing wrong"
        return f"{self.site}: {len(self.findings)} findings"


def _tags(book: Database, site: str) -> set[str]:
    return {
        str(row["tag"])
        for row in book.query("SELECT tag FROM trap_station WHERE site_code = ?", (site,))
    }


def audit_book(book: Database, site: SiteCode | str) -> BookAudit:
    """Walk one site's book looking for the inconsistencies keys cannot hold."""

    site_code = (site if isinstance(site, SiteCode) else SiteCode.parse(site)).value
    known = _tags(book, site_code)
    findings: list[BookFinding] = []

    for row in book.query(
        "SELECT number, tag FROM work_order WHERE site_code = ? ORDER BY number",
        (site_code,),
    ):
        if str(row["tag"]) not in known:
            findings.append(
                BookFinding(
                    "work order on an unknown tag",
                    f"{row['number']} is against {row['tag']}, which is not a station",
                )
            )

    for row in book.query(
        "SELECT route_code, tag FROM route_stop WHERE site_code = ? ORDER BY route_code, position",
        (site_code,),
    ):
        if str(row["tag"]) not in known:
            findings.append(
                BookFinding(
                    "route stop on an unknown tag",
                    f"route {row['route_code']} visits {row['tag']}, which is not a station",
                )
            )

    for row in book.query(
        "SELECT o.survey_reference, o.tag, o.observed_on FROM observation o "
        "JOIN trap_station s ON s.site_code = o.site_code AND s.tag = o.tag "
        "WHERE o.site_code = ? AND ("
        "  o.observed_on < s.installed_on "
        "  OR (s.removed_on IS NOT NULL AND o.observed_on >= s.removed_on)) "
        "ORDER BY o.tag",
        (site_code,),
    ):
        findings.append(
            BookFinding(
                "reading outside the station's life",
                f"{row['tag']} was read on {row['observed_on']} on survey "
                f"{row['survey_reference']}",
            )
        )

    for row in book.query(
        "SELECT s.reference FROM survey s WHERE s.site_code = ? AND NOT EXISTS ("
        "  SELECT 1 FROM observation o WHERE o.site_code = s.site_code "
        "  AND o.survey_reference = s.reference) ORDER BY s.reference",
        (site_code,),
    ):
        findings.append(BookFinding("survey with no readings", f"{row['reference']} is empty"))

    for row in book.query(
        "SELECT t.tag, m.code, m.max_operating_psia, h.operating_psia "
        "FROM trap_station t "
        "JOIN trap_model m ON m.manufacturer = t.model_manufacturer AND m.code = t.model_code "
        "JOIN header h ON h.site_code = t.site_code AND h.area_code = t.area_code "
        "  AND h.system_code = t.system_code "
        "WHERE t.site_code = ? AND m.max_operating_psia < h.operating_psia "
        "ORDER BY t.tag",
        (site_code,),
    ):
        findings.append(
            BookFinding(
                "trap under rated for its header",
                f"{row['tag']} carries {row['code']}, rated to "
                f"{float(row['max_operating_psia']) - 14.7:.0f} psig on a header at "
                f"{float(row['operating_psia']) - 14.7:.0f} psig",
            )
        )

    return BookAudit(site=site_code, findings=findings)
