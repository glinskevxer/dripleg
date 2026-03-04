"""Rules a site has switched off, and why.

Every so often a site has a genuine reason to disagree with a rule. The usual
one is a plant where the return line is at a pressure the flash rule was not
written for, and the hot outlet rule then fires on half the population. Rather
than argue the rule set down to the weakest site, the site switches that rule
off and says why.

Two things make this safe rather than a way of hiding findings. An exclusion
carries a reason and a date, so it appears in the report and can be reviewed.
And an exclusion naming a rule this build does not have is refused, so a rule
that gets renamed does not silently come back on at fifteen sites.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from dripleg.diagnosis.engine import DEFAULT_RULES
from dripleg.diagnosis.rules import RuleSet
from dripleg.errors import NotFoundError, ValidationError
from dripleg.model.tags import SiteCode
from dripleg.store.db import Database
from dripleg.store.keys import as_site

__all__ = ["RuleExclusion", "RulesRepository"]


@dataclass(frozen=True)
class RuleExclusion:
    """One rule a site does not run, with the reason it does not."""

    rule_code: str
    reason: str
    excluded_on: dt.date

    def __post_init__(self) -> None:
        code = self.rule_code.strip().upper()
        if not code:
            raise ValidationError("an exclusion names a rule", field="rule_code")
        object.__setattr__(self, "rule_code", code)
        reason = " ".join(self.reason.split())
        if not reason:
            raise ValidationError("an exclusion has to say why", field="reason")
        object.__setattr__(self, "reason", reason)

    def __str__(self) -> str:
        return f"{self.rule_code} off since {self.excluded_on}: {self.reason}"


class RulesRepository:
    """The exclusions one site carries."""

    def __init__(self, book: Database, rules: RuleSet | None = None) -> None:
        self.book = book
        self.rules = rules if rules is not None else DEFAULT_RULES

    def exclude(self, site: SiteCode | str, exclusion: RuleExclusion) -> None:
        if exclusion.rule_code not in self.rules:
            raise NotFoundError("rule", exclusion.rule_code)
        site_code = as_site(site)
        with self.book.transaction():
            self.book.execute(
                "INSERT INTO rule_exclusion (site_code, rule_code, reason, excluded_on) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(site_code, rule_code) DO UPDATE SET reason = excluded.reason, "
                "excluded_on = excluded.excluded_on",
                (
                    site_code.value,
                    exclusion.rule_code,
                    exclusion.reason,
                    exclusion.excluded_on.isoformat(),
                ),
            )

    def include(self, site: SiteCode | str, rule_code: str) -> bool:
        """Switch a rule back on. Says whether it was off in the first place."""

        site_code = as_site(site)
        wanted = rule_code.strip().upper()
        before = self.book.scalar(
            "SELECT COUNT(*) FROM rule_exclusion WHERE site_code = ? AND rule_code = ?",
            (site_code.value, wanted),
        )
        with self.book.transaction():
            self.book.execute(
                "DELETE FROM rule_exclusion WHERE site_code = ? AND rule_code = ?",
                (site_code.value, wanted),
            )
        return bool(before)

    def exclusions(self, site: SiteCode | str) -> list[RuleExclusion]:
        site_code = as_site(site)
        rows = self.book.query(
            "SELECT * FROM rule_exclusion WHERE site_code = ? ORDER BY rule_code",
            (site_code.value,),
        )
        return [
            RuleExclusion(
                rule_code=str(row["rule_code"]),
                reason=str(row["reason"]),
                excluded_on=dt.date.fromisoformat(str(row["excluded_on"])),
            )
            for row in rows
        ]

    def rule_set_for(self, site: SiteCode | str) -> RuleSet:
        """The rule set this site actually runs.

        An exclusion naming a rule that is no longer in the build is skipped
        rather than raised, because the book outlives the build and a removed
        rule cannot be run either way.
        """

        excluded = [
            exclusion.rule_code
            for exclusion in self.exclusions(site)
            if exclusion.rule_code in self.rules
        ]
        if not excluded:
            return self.rules
        return self.rules.without(*excluded)

    def stale_exclusions(self, site: SiteCode | str) -> list[RuleExclusion]:
        """Exclusions naming rules this build does not have any more."""

        return [
            exclusion
            for exclusion in self.exclusions(site)
            if exclusion.rule_code not in self.rules
        ]
