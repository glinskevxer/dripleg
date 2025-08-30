from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from decimal import Decimal

import pytest

from dripleg.errors import NotFoundError
from dripleg.loss.cost import CostBasis
from dripleg.loss.emissions import factor_named
from dripleg.loss.energy import EnergyModel
from dripleg.model.plant import Site
from dripleg.repair.recommend import RepairBasis
from dripleg.store.basis_repo import BasisRepository, SiteBasis
from dripleg.store.db import Database
from dripleg.store.migrations import migrate
from dripleg.store.plant_repo import PlantRepository
from dripleg.units.money import Money, Price
from dripleg.units.temperature import Temperature


@pytest.fixture
def book() -> Iterator[Database]:
    db = Database()
    migrate(db)
    PlantRepository(db).save_site(Site.of("WRX1", "Mill", "Bryn"))
    yield db
    db.close()


def a_basis() -> SiteBasis:
    return SiteBasis(
        costs=CostBasis(
            fuel=Price.of("6.2537", "MMBtu"),
            water=Price.of("4.10", "1000 gal"),
            effluent=Price.of("3.40", "1000 gal"),
            chemical=Price.of("2.75", "1000 gal"),
        ),
        energy=EnergyModel(
            feedwater_temperature=Temperature.from_fahrenheit(219.0),
            boiler_efficiency=0.845,
            condensate_returned=0.68,
            receiver_vent_fraction=0.4,
        ),
        repairs=RepairBasis(
            labour=Price.of("81.50", "h"), permit_cost=Money.from_dollars("150.00")
        ),
        factor=factor_named("fuel oil 2"),
        effective_from=dt.date(2025, 4, 1),
    )


def test_a_basis_round_trips(book: Database) -> None:
    repo = BasisRepository(book)
    repo.save("WRX1", a_basis())
    stored = repo.get("WRX1")
    assert stored == a_basis()


def test_a_price_keeps_every_digit_it_was_given(book: Database) -> None:
    repo = BasisRepository(book)
    repo.save("WRX1", a_basis())
    assert repo.get("WRX1").costs.fuel.dollars_per_unit == Decimal("6.2537")


def test_saving_twice_updates_the_row(book: Database) -> None:
    repo = BasisRepository(book)
    repo.save("WRX1", a_basis())
    repo.save("WRX1", SiteBasis.typical(dt.date(2026, 1, 1)))
    stored = repo.get("WRX1")
    assert stored.effective_from == dt.date(2026, 1, 1)
    assert stored.factor.name == "natural gas"
    assert book.scalar("SELECT COUNT(*) FROM cost_basis") == 1


def test_a_site_with_no_basis(book: Database) -> None:
    repo = BasisRepository(book)
    with pytest.raises(NotFoundError, match="cost basis"):
        repo.get("WRX1")
    fallback = repo.get_or_default("WRX1")
    assert fallback == SiteBasis.typical()


def test_the_typical_basis_is_a_worked_example() -> None:
    basis = SiteBasis.typical()
    assert basis.costs.fuel.unit == "MMBtu"
    assert basis.energy.boiler_efficiency == pytest.approx(0.82)
    assert basis.repairs.labour.unit == "h"
    assert basis.factor.name == "natural gas"


def test_the_facts_block_names_everything_a_costing_uses() -> None:
    facts = a_basis().facts()
    assert facts["fuel"] == "$6.2537/MMBtu"
    assert facts["labour"] == "$81.5/h"
    assert facts["permit"] == "$150.00"
    assert facts["feedwater_f"] == pytest.approx(219.0)
    assert facts["emissions_factor"] == "number 2 fuel oil"
    assert facts["effective_from"] == "2025-04-01"


def test_the_schema_holds_the_fractions(book: Database) -> None:
    repo = BasisRepository(book)
    repo.save("WRX1", a_basis())
    with pytest.raises(Exception, match="CHECK constraint failed"):
        book.execute("UPDATE cost_basis SET boiler_efficiency = 1.4")
    with pytest.raises(Exception, match="CHECK constraint failed"):
        book.execute("UPDATE cost_basis SET condensate_returned = -0.1")
    with pytest.raises(Exception, match="CHECK constraint failed"):
        book.execute("UPDATE cost_basis SET feedwater_f = 20")


def test_a_basis_goes_when_the_site_goes(book: Database) -> None:
    BasisRepository(book).save("WRX1", a_basis())
    book.execute("DELETE FROM site WHERE code = 'WRX1'")
    assert book.scalar("SELECT COUNT(*) FROM cost_basis") == 0
