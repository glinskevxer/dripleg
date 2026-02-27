from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import pytest

from dripleg.diagnosis.engine import DEFAULT_RULES
from dripleg.errors import NotFoundError, ValidationError
from dripleg.model.plant import Site
from dripleg.store.db import Database
from dripleg.store.migrations import migrate
from dripleg.store.plant_repo import PlantRepository
from dripleg.store.rules_repo import RuleExclusion, RulesRepository

WHEN = dt.date(2025, 4, 14)


@pytest.fixture
def book() -> Iterator[Database]:
    db = Database()
    migrate(db)
    PlantRepository(db).save_site(Site.of("WRX1", "Mill", "Bryn"))
    yield db
    db.close()


def an_exclusion(code: str = "TMP-1") -> RuleExclusion:
    return RuleExclusion(
        rule_code=code,
        reason="the return line here runs hot enough to fire this on everything",
        excluded_on=WHEN,
    )


def test_an_exclusion_normalises_its_code_and_reason() -> None:
    exclusion = RuleExclusion(" tmp-1 ", "  a good   reason ", WHEN)
    assert exclusion.rule_code == "TMP-1"
    assert exclusion.reason == "a good reason"


def test_an_exclusion_needs_a_rule_and_a_reason() -> None:
    with pytest.raises(ValidationError, match="names a rule"):
        RuleExclusion("  ", "a reason", WHEN)
    with pytest.raises(ValidationError, match="say why"):
        RuleExclusion("TMP-1", "   ", WHEN)


def test_an_exclusion_round_trips(book: Database) -> None:
    repo = RulesRepository(book)
    repo.exclude("WRX1", an_exclusion())
    stored = repo.exclusions("WRX1")
    assert len(stored) == 1
    assert stored[0].rule_code == "TMP-1"
    assert stored[0].excluded_on == WHEN


def test_excluding_a_rule_this_build_does_not_have_is_refused(book: Database) -> None:
    repo = RulesRepository(book)
    with pytest.raises(NotFoundError, match="rule"):
        repo.exclude("WRX1", an_exclusion("ZZZ-9"))


def test_excluding_twice_updates_the_reason(book: Database) -> None:
    repo = RulesRepository(book)
    repo.exclude("WRX1", an_exclusion())
    repo.exclude("WRX1", RuleExclusion("TMP-1", "a different reason", WHEN))
    stored = repo.exclusions("WRX1")
    assert len(stored) == 1
    assert stored[0].reason == "a different reason"


def test_the_rule_set_drops_what_is_excluded(book: Database) -> None:
    repo = RulesRepository(book)
    assert repo.rule_set_for("WRX1") is DEFAULT_RULES
    repo.exclude("WRX1", an_exclusion())
    trimmed = repo.rule_set_for("WRX1")
    assert "TMP-1" not in trimmed
    assert len(trimmed) == len(DEFAULT_RULES) - 1


def test_several_exclusions_all_come_off(book: Database) -> None:
    repo = RulesRepository(book)
    repo.exclude("WRX1", an_exclusion("TMP-1"))
    repo.exclude("WRX1", an_exclusion("SND-2"))
    trimmed = repo.rule_set_for("WRX1")
    assert len(trimmed) == len(DEFAULT_RULES) - 2


def test_switching_a_rule_back_on(book: Database) -> None:
    repo = RulesRepository(book)
    repo.exclude("WRX1", an_exclusion())
    assert repo.include("WRX1", "tmp-1")
    assert repo.exclusions("WRX1") == []
    assert not repo.include("WRX1", "TMP-1")


def test_an_exclusion_naming_a_rule_that_has_gone_is_skipped(book: Database) -> None:
    repo = RulesRepository(book)
    repo.exclude("WRX1", an_exclusion())
    book.execute("UPDATE rule_exclusion SET rule_code = 'GONE-1'")
    assert repo.rule_set_for("WRX1") is DEFAULT_RULES
    stale = repo.stale_exclusions("WRX1")
    assert [e.rule_code for e in stale] == ["GONE-1"]


def test_the_schema_will_not_take_a_blank_reason(book: Database) -> None:
    with pytest.raises(Exception, match="CHECK constraint failed"):
        book.execute(
            "INSERT INTO rule_exclusion (site_code, rule_code, reason, excluded_on) "
            "VALUES (?, ?, ?, ?)",
            ("WRX1", "TMP-1", "   ", "2025-04-14"),
        )


def test_exclusions_go_when_the_site_goes(book: Database) -> None:
    RulesRepository(book).exclude("WRX1", an_exclusion())
    book.execute("DELETE FROM site WHERE code = 'WRX1'")
    assert book.scalar("SELECT COUNT(*) FROM rule_exclusion") == 0


def test_printing_an_exclusion() -> None:
    assert str(an_exclusion()).startswith("TMP-1 off since 2025-04-14: ")
