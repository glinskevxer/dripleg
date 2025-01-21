"""Money in whole cents, and unit prices in exact decimal.

A loss register is read by people who then sign a purchase order against it, so
the numbers have to add up when they are added up a second time by somebody
else. Floats do not do that. Money is an integer count of cents, prices are
Decimal, and the only place a rounding decision happens is where a price meets
a quantity, which is one method with one rule.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from dripleg.errors import ValidationError

__all__ = ["Money", "Price"]

_MONEY_TEXT = re.compile(r"^\s*\$?\s*(?P<sign>-)?\$?\s*(?P<value>[0-9,]*\.?[0-9]+)\s*$")


def _to_decimal(value: Decimal | int | float | str, field: str) -> Decimal:
    if isinstance(value, Decimal):
        candidate = value
    elif isinstance(value, int):
        candidate = Decimal(value)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValidationError(f"{field} is not a finite number", field=field)
        candidate = Decimal(str(value))
    else:
        try:
            candidate = Decimal(value.replace(",", "").replace("$", "").strip())
        except InvalidOperation:
            raise ValidationError(f"cannot read {value!r} as {field}", field=field) from None
    if not candidate.is_finite():
        raise ValidationError(f"{field} is not a finite number", field=field)
    return candidate


@dataclass(frozen=True, order=True)
class Money:
    """An amount, held as a whole number of cents. May be negative."""

    cents: int

    def __post_init__(self) -> None:
        if not isinstance(self.cents, int) or isinstance(self.cents, bool):
            raise ValidationError("money is a whole number of cents", field="money")

    @classmethod
    def zero(cls) -> Money:
        return cls(0)

    @classmethod
    def from_cents(cls, cents: int) -> Money:
        return cls(cents)

    @classmethod
    def from_dollars(cls, value: Decimal | int | float | str) -> Money:
        amount = _to_decimal(value, "money")
        return cls(int(amount.scaleb(2).quantize(Decimal(1), rounding=ROUND_HALF_UP)))

    @classmethod
    def parse(cls, text: str) -> Money:
        match = _MONEY_TEXT.match(text)
        if match is None:
            raise ValidationError(f"cannot read {text!r} as money", field="money")
        sign = -1 if match.group("sign") else 1
        return cls.from_dollars(Decimal(match.group("value").replace(",", "")) * sign)

    @property
    def dollars(self) -> Decimal:
        return (Decimal(self.cents) / 100).quantize(Decimal("0.01"))

    @property
    def is_zero(self) -> bool:
        return self.cents == 0

    def __add__(self, other: Money) -> Money:
        return Money(self.cents + other.cents)

    def __sub__(self, other: Money) -> Money:
        return Money(self.cents - other.cents)

    def __neg__(self) -> Money:
        return Money(-self.cents)

    def __abs__(self) -> Money:
        return Money(abs(self.cents))

    def scaled(self, factor: Decimal | int | float | str) -> Money:
        """Take a fraction of this amount, rounding half up to the cent."""

        multiplier = _to_decimal(factor, "factor")
        product = Decimal(self.cents) * multiplier
        return Money(int(product.quantize(Decimal(1), rounding=ROUND_HALF_UP)))

    def allocate(self, weights: list[float]) -> list[Money]:
        """Split this amount across weights, largest remainder first.

        Used to push a header's fuel cost back onto the traps hanging off it.
        The parts always add back to the whole, which is the point.
        """

        if not weights:
            raise ValidationError("cannot allocate across no weights", field="weights")
        if any(w < 0 for w in weights):
            raise ValidationError("allocation weights cannot be negative", field="weights")
        total = sum(weights)
        if total <= 0:
            raise ValidationError(
                "allocation weights have to add to more than zero", field="weights"
            )
        exact = [
            Decimal(self.cents) * _to_decimal(w, "weights") / _to_decimal(total, "weights")
            for w in weights
        ]
        floors = [int(x.to_integral_value(rounding="ROUND_FLOOR")) for x in exact]
        remainder = self.cents - sum(floors)
        order = sorted(range(len(weights)), key=lambda i: (exact[i] - floors[i]), reverse=True)
        step = 1 if remainder >= 0 else -1
        for k in range(abs(remainder)):
            floors[order[k % len(order)]] += step
        return [Money(c) for c in floors]

    def payback_years(self, annual_saving: Money) -> float | None:
        """Simple payback on this amount of repair cost. None if it never pays."""

        if annual_saving.cents <= 0:
            return None
        return self.cents / annual_saving.cents

    def __str__(self) -> str:
        sign = "-" if self.cents < 0 else ""
        whole, part = divmod(abs(self.cents), 100)
        return f"{sign}${whole:,}.{part:02d}"

    def __repr__(self) -> str:
        return f"Money(cents={self.cents})"


@dataclass(frozen=True, order=True)
class Price:
    """A price per unit of something, exact to as many places as it was given.

    Natural gas is quoted to the tenth of a cent per MMBtu and treatment
    chemical to the cent per thousand gallons, so the price itself is never
    rounded. Rounding waits for the multiplication.
    """

    dollars_per_unit: Decimal
    unit: str

    def __post_init__(self) -> None:
        if not self.dollars_per_unit.is_finite():
            raise ValidationError("price is not a finite number", field="price")
        if self.dollars_per_unit < 0:
            raise ValidationError("price cannot be negative", field="price")
        if not self.unit.strip():
            raise ValidationError("a price has to say what it is per", field="unit")

    @classmethod
    def of(cls, value: Decimal | int | float | str, unit: str) -> Price:
        return cls(_to_decimal(value, "price"), unit.strip())

    def times(self, quantity: Decimal | int | float) -> Money:
        """Multiply by a quantity of the unit and round to the cent."""

        amount = _to_decimal(quantity, "quantity")
        if amount < 0:
            raise ValidationError("cannot price a negative quantity", field="quantity")
        return Money.from_dollars(self.dollars_per_unit * amount)

    def __str__(self) -> str:
        return f"${self.dollars_per_unit.normalize():f}/{self.unit}"
