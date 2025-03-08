from __future__ import annotations

import pytest

from dripleg.errors import NotFoundError, ValidationError
from dripleg.model.catalogue import ConnectionType, TrapCatalogue, TrapModel
from dripleg.model.operating import OperatingProfile, ServicePattern
from dripleg.model.principles import OperatingPrinciple
from dripleg.store.catalogue_repo import CatalogueRepository, ProfileRepository
from dripleg.store.codes import enum_from_value, months_from_text, months_to_text
from dripleg.store.db import Database
from dripleg.store.migrations import migrate
from dripleg.units.money import Money
from dripleg.units.pressure import Pressure


@pytest.fixture
def book() -> Database:
    db = Database()
    migrate(db)
    db.execute(
        "INSERT INTO site (code, name, operator, fuel_price_basis) VALUES (?, ?, ?, ?)",
        ("WRX1", "Mill", "Bryn", "gas"),
    )
    return db


def a_model(code: str = "TD52", **overrides: object) -> TrapModel:
    fields: dict[str, object] = {
        "manufacturer": "Halden",
        "code": code,
        "principle": OperatingPrinciple.THERMODYNAMIC_DISC,
        "orifice_diameter_in": 0.093,
        "max_operating_pressure": Pressure.from_psig(600.0),
        "max_back_pressure_percent": 80.0,
        "connection_size_in": 0.5,
        "connection_type": ConnectionType.SCREWED,
        "list_price": Money.from_dollars("184.00"),
    }
    fields.update(overrides)
    return TrapModel(**fields)  # type: ignore[arg-type]


def test_a_model_round_trips(book: Database) -> None:
    repo = CatalogueRepository(book)
    repo.save(a_model())
    stored = repo.get("halden", "td52")
    assert stored.principle is OperatingPrinciple.THERMODYNAMIC_DISC
    assert stored.list_price == Money.from_dollars("184.00")
    assert stored.max_operating_pressure.psig == pytest.approx(600.0)
    assert stored.connection_type == ConnectionType.SCREWED


def test_saving_a_model_twice_updates_it(book: Database) -> None:
    repo = CatalogueRepository(book)
    repo.save(a_model())
    repo.save(a_model(list_price=Money.from_dollars("199.00")))
    assert repo.get("Halden", "TD52").list_price == Money.from_dollars("199.00")
    assert len(repo.load_catalogue()) == 1


def test_a_discontinued_model_keeps_its_successor(book: Database) -> None:
    repo = CatalogueRepository(book)
    repo.save(a_model("TD75"))
    repo.save(a_model(discontinued=True, replaced_by="TD75"))
    stored = repo.get("Halden", "TD52")
    assert stored.discontinued
    assert stored.replaced_by == "TD75"
    assert not stored.is_orderable()


def test_a_missing_model(book: Database) -> None:
    repo = CatalogueRepository(book)
    with pytest.raises(NotFoundError, match="trap model"):
        repo.get("Halden", "NOPE")
    assert repo.find("Halden", "NOPE") is None


def test_a_whole_catalogue_goes_in_and_comes_back(book: Database) -> None:
    repo = CatalogueRepository(book)
    catalogue = TrapCatalogue(
        [
            a_model("TD52"),
            a_model("IB18", principle=OperatingPrinciple.INVERTED_BUCKET),
            a_model("FT40", principle=OperatingPrinciple.FLOAT_THERMOSTATIC),
        ]
    )
    assert repo.save_catalogue(catalogue) == 3
    loaded = repo.load_catalogue()
    assert len(loaded) == 3
    assert [m.code for m in loaded] == ["FT40", "IB18", "TD52"]


def test_a_principle_the_build_does_not_know(book: Database) -> None:
    repo = CatalogueRepository(book)
    repo.save(a_model())
    book.execute("UPDATE trap_model SET principle = 'magic'")
    with pytest.raises(ValidationError, match="not an operating principle"):
        repo.get("Halden", "TD52")


def test_a_profile_round_trips(book: Database) -> None:
    repo = ProfileRepository(book)
    repo.save("WRX1", OperatingProfile.continuous())
    stored = repo.get("WRX1", "CONT")
    assert stored.pattern is ServicePattern.CONTINUOUS
    assert stored.load_factor == pytest.approx(1.0)


def test_a_campaign_profile_keeps_its_months(book: Database) -> None:
    repo = ProfileRepository(book)
    profile = OperatingProfile(
        "CAMP",
        "Beet campaign",
        ServicePattern.CAMPAIGN,
        campaign_months=frozenset({9, 10, 11, 12, 1}),
    )
    repo.save("WRX1", profile)
    assert repo.get("WRX1", "CAMP") == profile


def test_saving_a_profile_twice_updates_it(book: Database) -> None:
    repo = ProfileRepository(book)
    repo.save("WRX1", OperatingProfile("TRC", "Tracer", load_factor=1.0))
    repo.save("WRX1", OperatingProfile("TRC", "Tracer", load_factor=0.35))
    assert repo.get("WRX1", "TRC").load_factor == pytest.approx(0.35)
    assert len(repo.list_for("WRX1")) == 1


def test_profiles_list_in_code_order(book: Database) -> None:
    repo = ProfileRepository(book)
    repo.save("WRX1", OperatingProfile("TRC", "Tracer"))
    repo.save("WRX1", OperatingProfile.continuous())
    assert [p.code for p in repo.list_for("WRX1")] == ["CONT", "TRC"]


def test_a_missing_profile(book: Database) -> None:
    with pytest.raises(NotFoundError, match="operating profile"):
        ProfileRepository(book).get("WRX1", "NOPE")


def test_the_enum_lookup_says_what_it_wanted() -> None:
    assert enum_from_value(ServicePattern, "CONTINUOUS") is ServicePattern.CONTINUOUS
    with pytest.raises(ValidationError, match="expected one of: campaign"):
        enum_from_value(ServicePattern, "sometimes")


def test_the_enum_lookup_names_the_enum_in_words() -> None:
    with pytest.raises(ValidationError, match="not a service pattern"):
        enum_from_value(ServicePattern, "nope")
    with pytest.raises(ValidationError, match="not an operating principle"):
        enum_from_value(OperatingPrinciple, "nope")


def test_campaign_months_round_trip_through_text() -> None:
    months = frozenset({9, 10, 11, 12, 1})
    assert months_to_text(months) == "1,9,10,11,12"
    assert months_from_text("1,9,10,11,12") == months
    assert months_from_text("  ") == frozenset()
    assert months_from_text(" 3 , 4 ") == frozenset({3, 4})


def test_a_bad_month_list_is_caught() -> None:
    with pytest.raises(ValidationError, match="not a month number"):
        months_from_text("3,april")
