from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import pytest

from dripleg.errors import NotFoundError, ValidationError
from dripleg.model.operating import OperatingProfile
from dripleg.model.plant import Site
from dripleg.model.tags import TrapTag
from dripleg.store.catalogue_repo import CatalogueRepository, ProfileRepository
from dripleg.store.db import Database
from dripleg.store.migrations import migrate
from dripleg.store.plant_repo import PlantRepository
from dripleg.store.risk_repo import AcceptedRisk, RiskRepository
from dripleg.store.station_repo import StationRepository
from tests.support.build import a_model, a_station, header_for

ACCEPTED = dt.date(2025, 4, 14)
REVIEW = dt.date(2026, 4, 14)


@pytest.fixture
def book() -> Iterator[Database]:
    db = Database()
    migrate(db)
    plant = PlantRepository(db)
    plant.save_site(Site.of("WRX1", "Mill", "Bryn"))
    from dripleg.model.plant import Area

    plant.save_area(Area.of("WRX1", "B12", "Machine", "PM2"))
    plant.save_header(header_for(TrapTag.parse("B12-MP-1")))
    CatalogueRepository(db).save(a_model())
    ProfileRepository(db).save("WRX1", OperatingProfile.continuous())
    StationRepository(db).save(a_station(tag=TrapTag.parse("B12-MP-1")))
    yield db
    db.close()


def a_risk(tag: str = "B12-MP-0001", **overrides: object) -> AcceptedRisk:
    fields: dict[str, object] = {
        "tag": TrapTag.parse(tag),
        "reason": "the line comes down in six weeks",
        "accepted_by": "H Weir",
        "accepted_on": ACCEPTED,
        "review_on": REVIEW,
    }
    fields.update(overrides)
    return AcceptedRisk(**fields)  # type: ignore[arg-type]


def test_an_acceptance_normalises_its_text() -> None:
    risk = a_risk(reason="  the   line comes down ", accepted_by="  H   Weir ")
    assert risk.reason == "the line comes down"
    assert risk.accepted_by == "H Weir"


def test_an_acceptance_needs_a_reason_and_a_name() -> None:
    with pytest.raises(ValidationError, match="say why"):
        a_risk(reason="  ")
    with pytest.raises(ValidationError, match="who made it"):
        a_risk(accepted_by=" ")


def test_an_acceptance_is_reviewed_later_than_it_is_made() -> None:
    with pytest.raises(ValidationError, match="reviewed later"):
        a_risk(review_on=ACCEPTED)


def test_an_acceptance_is_live_until_its_review_date() -> None:
    risk = a_risk()
    assert not risk.is_live_on(ACCEPTED - dt.timedelta(days=1))
    assert risk.is_live_on(ACCEPTED)
    assert risk.is_live_on(REVIEW - dt.timedelta(days=1))
    assert not risk.is_live_on(REVIEW)


def test_the_days_left_run_down_to_nothing() -> None:
    risk = a_risk()
    assert risk.days_left_on(ACCEPTED) == 365
    assert risk.days_left_on(REVIEW) == 0
    assert risk.days_left_on(REVIEW + dt.timedelta(days=30)) == 0


def test_an_acceptance_round_trips(book: Database) -> None:
    repo = RiskRepository(book)
    repo.accept("WRX1", a_risk())
    stored = repo.all_for("WRX1")
    assert stored == [a_risk()]


def test_accepting_a_trap_that_is_not_a_station_is_refused(book: Database) -> None:
    with pytest.raises(NotFoundError, match="trap station"):
        RiskRepository(book).accept("WRX1", a_risk("B12-MP-0099"))


def test_accepting_twice_updates_the_reason(book: Database) -> None:
    repo = RiskRepository(book)
    repo.accept("WRX1", a_risk())
    repo.accept("WRX1", a_risk(reason="no budget this year"))
    stored = repo.all_for("WRX1")
    assert len(stored) == 1
    assert stored[0].reason == "no budget this year"


def test_withdrawing_says_whether_there_was_one(book: Database) -> None:
    repo = RiskRepository(book)
    repo.accept("WRX1", a_risk())
    assert repo.withdraw("WRX1", "B12-MP-1")
    assert repo.all_for("WRX1") == []
    assert not repo.withdraw("WRX1", "B12-MP-1")


def test_the_live_acceptances_are_keyed_by_tag(book: Database) -> None:
    repo = RiskRepository(book)
    repo.accept("WRX1", a_risk())
    live = repo.live_on("WRX1", ACCEPTED + dt.timedelta(days=30))
    assert list(live) == [TrapTag.parse("B12-MP-1")]
    assert repo.live_on("WRX1", REVIEW) == {}


def test_an_expired_acceptance_is_due_for_review(book: Database) -> None:
    repo = RiskRepository(book)
    repo.accept("WRX1", a_risk())
    assert repo.due_for_review("WRX1", ACCEPTED + dt.timedelta(days=30)) == []
    assert len(repo.due_for_review("WRX1", REVIEW)) == 1


def test_the_schema_holds_the_dates_and_the_text(book: Database) -> None:
    with pytest.raises(Exception, match="CHECK constraint failed"):
        book.execute(
            "INSERT INTO accepted_risk (site_code, tag, reason, accepted_by, "
            "accepted_on, review_on) VALUES (?, ?, ?, ?, ?, ?)",
            ("WRX1", "B12-MP-0001", "a reason", "H Weir", "2025-04-14", "2025-04-14"),
        )
    with pytest.raises(Exception, match="CHECK constraint failed"):
        book.execute(
            "INSERT INTO accepted_risk (site_code, tag, reason, accepted_by, "
            "accepted_on, review_on) VALUES (?, ?, ?, ?, ?, ?)",
            ("WRX1", "B12-MP-0001", "   ", "H Weir", "2025-04-14", "2026-04-14"),
        )


def test_an_acceptance_goes_when_the_station_goes(book: Database) -> None:
    RiskRepository(book).accept("WRX1", a_risk())
    book.execute("DELETE FROM trap_station")
    assert book.scalar("SELECT COUNT(*) FROM accepted_risk") == 0


def test_printing_an_acceptance() -> None:
    assert str(a_risk()) == (
        "B12-MP-0001 accepted by H Weir on 2025-04-14, back on the list 2026-04-14"
    )
