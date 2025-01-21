from __future__ import annotations

from decimal import Decimal

import pytest

from dripleg.errors import ValidationError
from dripleg.units.money import Money, Price


def test_dollars_go_in_and_come_back() -> None:
    assert Money.from_dollars("12.34").cents == 1234
    assert Money.from_dollars(12.34).dollars == Decimal("12.34")
    assert Money.from_cents(1234).dollars == Decimal("12.34")


def test_half_a_cent_rounds_up() -> None:
    assert Money.from_dollars("0.005").cents == 1
    assert Money.from_dollars(Decimal("1.115")).cents == 112


def test_parse_takes_the_dollar_sign_and_the_commas() -> None:
    assert Money.parse("$1,234.56").cents == 123456
    assert Money.parse("-$40").cents == -4000
    assert Money.parse(" 7 ").cents == 700


def test_parse_refuses_rubbish() -> None:
    with pytest.raises(ValidationError, match="cannot read"):
        Money.parse("free")


def test_money_is_whole_cents_only() -> None:
    with pytest.raises(ValidationError, match="whole number of cents"):
        Money(12.5)  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="finite"):
        Money.from_dollars(float("inf"))
    with pytest.raises(ValidationError, match="cannot read"):
        Money.from_dollars("about ten")


def test_arithmetic() -> None:
    a = Money.from_dollars("10.00")
    b = Money.from_dollars("2.50")
    assert (a + b).cents == 1250
    assert (a - b).cents == 750
    assert (-b).cents == -250
    assert abs(Money.from_cents(-250)).cents == 250
    assert Money.zero().is_zero


def test_scaling_rounds_half_up() -> None:
    assert Money.from_dollars("10.00").scaled("0.255").cents == 255
    assert Money.from_dollars("100.00").scaled(Decimal("0.5")).cents == 5000
    assert Money.from_cents(1).scaled(0.5).cents == 1


def test_allocation_adds_back_to_the_whole() -> None:
    parts = Money.from_dollars("100.00").allocate([1.0, 1.0, 1.0])
    assert [p.cents for p in parts] == [3334, 3333, 3333]
    assert sum(p.cents for p in parts) == 10000


def test_allocation_follows_the_weights() -> None:
    parts = Money.from_dollars("1000.00").allocate([50.0, 30.0, 20.0])
    assert [p.dollars for p in parts] == [Decimal("500.00"), Decimal("300.00"), Decimal("200.00")]


def test_allocation_gives_the_odd_cent_to_the_biggest_remainder() -> None:
    parts = Money.from_cents(10).allocate([1.0, 2.0])
    assert [p.cents for p in parts] == [3, 7]


def test_a_negative_amount_allocates_too() -> None:
    parts = Money.from_cents(-10).allocate([1.0, 1.0, 1.0])
    assert sum(p.cents for p in parts) == -10


def test_allocation_refuses_nonsense_weights() -> None:
    with pytest.raises(ValidationError, match="no weights"):
        Money.from_cents(100).allocate([])
    with pytest.raises(ValidationError, match="cannot be negative"):
        Money.from_cents(100).allocate([1.0, -1.0])
    with pytest.raises(ValidationError, match="more than zero"):
        Money.from_cents(100).allocate([0.0, 0.0])


def test_payback_is_cost_over_saving() -> None:
    cost = Money.from_dollars("400.00")
    assert cost.payback_years(Money.from_dollars("1600.00")) == pytest.approx(0.25)
    assert cost.payback_years(Money.zero()) is None
    assert cost.payback_years(Money.from_cents(-5)) is None


def test_printing_money() -> None:
    assert str(Money.from_dollars("1234.50")) == "$1,234.50"
    assert str(Money.from_cents(-5)) == "-$0.05"
    assert repr(Money.from_cents(5)) == "Money(cents=5)"


def test_a_price_multiplies_into_money() -> None:
    gas = Price.of("6.25", "MMBtu")
    assert gas.times(160.0).dollars == Decimal("1000.00")
    assert gas.times(Decimal("0.5")).cents == 313


def test_a_price_keeps_its_own_precision() -> None:
    gas = Price.of("6.2537", "MMBtu")
    assert gas.dollars_per_unit == Decimal("6.2537")
    assert str(gas) == "$6.2537/MMBtu"


def test_a_price_refuses_bad_input() -> None:
    with pytest.raises(ValidationError, match="cannot be negative"):
        Price.of("-1", "MMBtu")
    with pytest.raises(ValidationError, match="what it is per"):
        Price.of("1", "  ")
    with pytest.raises(ValidationError, match="negative quantity"):
        Price.of("1", "MMBtu").times(-1)
    with pytest.raises(ValidationError, match="finite"):
        Price.of(float("nan"), "MMBtu")


def test_prices_sort_by_rate() -> None:
    cheap = Price.of("3.10", "MMBtu")
    dear = Price.of("9.40", "MMBtu")
    assert min(cheap, dear) == cheap
