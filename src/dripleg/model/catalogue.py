"""The trap models a site actually buys, and what each one can be asked to do.

Every trap on the register points at a catalogue entry rather than carrying a
manufacturer string. It is the only way a reliability report can say that the
half inch discs on the medium pressure headers are failing at four times the
rate of everything else, and the only way a replacement recommendation can name
something the storeroom stocks.

The two limits that matter are the maximum operating pressure, which is a
safety and a warranty question, and the maximum back pressure, which is a
performance one and is quoted as a percentage of inlet pressure.

Manufacturer and code are both held upper case, the way a parts list prints
them. That is not a cosmetic choice: the catalogue is keyed on the pair, and a
book that has taken `Halden` once and `HALDEN` once has two of everything.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterator
from dataclasses import dataclass

from dripleg.errors import ConflictError, NotFoundError, ValidationError
from dripleg.model.header import SteamHeader
from dripleg.model.principles import OperatingPrinciple
from dripleg.units.money import Money
from dripleg.units.pressure import Pressure

__all__ = ["ConnectionType", "TrapCatalogue", "TrapModel"]

_CODE = re.compile(r"^[A-Z0-9][A-Z0-9./-]{1,23}$")

MIN_ORIFICE_IN = 0.008
MAX_ORIFICE_IN = 1.5


class ConnectionType:
    """Named constants rather than an enum, because the list grows locally."""

    SCREWED = "screwed"
    SOCKET_WELD = "socket_weld"
    FLANGED = "flanged"
    UNIVERSAL_CONNECTOR = "universal_connector"
    SWIVEL = "swivel"

    ALL = frozenset(
        {SCREWED, SOCKET_WELD, FLANGED, UNIVERSAL_CONNECTOR, SWIVEL},
    )


@dataclass(frozen=True)
class TrapModel:
    """One catalogue entry: a manufacturer's model at one orifice size."""

    manufacturer: str
    code: str
    principle: OperatingPrinciple
    orifice_diameter_in: float
    max_operating_pressure: Pressure
    max_back_pressure_percent: float
    connection_size_in: float
    connection_type: str
    list_price: Money
    discontinued: bool = False
    replaced_by: str | None = None
    warranty_months: int = 12

    def __post_init__(self) -> None:
        maker = " ".join(self.manufacturer.split()).upper()
        if not maker:
            raise ValidationError("a model needs a manufacturer", field="manufacturer")
        object.__setattr__(self, "manufacturer", maker)
        code = self.code.strip().upper()
        if not _CODE.match(code):
            raise ValidationError(f"{self.code!r} is not a model code", field="code")
        object.__setattr__(self, "code", code)
        if not MIN_ORIFICE_IN <= self.orifice_diameter_in <= MAX_ORIFICE_IN:
            raise ValidationError(
                f"an orifice of {self.orifice_diameter_in:g} inch is not a trap orifice",
                field="orifice_diameter_in",
            )
        if not 0.0 < self.max_back_pressure_percent <= 100.0:
            raise ValidationError(
                "the back pressure limit is a percentage of inlet pressure",
                field="max_back_pressure_percent",
            )
        if self.connection_size_in <= 0:
            raise ValidationError("a connection has a size", field="connection_size_in")
        if self.connection_type not in ConnectionType.ALL:
            raise ValidationError(
                f"{self.connection_type!r} is not a connection this site fits",
                field="connection_type",
            )
        if self.list_price.cents < 0:
            raise ValidationError("a list price is not negative", field="list_price")
        if not 0 <= self.warranty_months <= 120:
            raise ValidationError(
                "a warranty runs from nothing to ten years", field="warranty_months"
            )
        if self.replaced_by is not None and not self.discontinued:
            raise ValidationError(
                "only a discontinued model is replaced by another one",
                field="replaced_by",
            )
        if self.replaced_by is not None and self.replaced_by.strip().upper() == self.code:
            raise ValidationError("a model cannot replace itself", field="replaced_by")

    @property
    def key(self) -> tuple[str, str]:
        return (self.manufacturer, self.code)

    @property
    def orifice_area_sq_in(self) -> float:
        return math.pi * (self.orifice_diameter_in / 2.0) ** 2

    def suits_pressure(self, pressure: Pressure) -> bool:
        return pressure <= self.max_operating_pressure

    def back_pressure_limit_at(self, inlet: Pressure) -> Pressure:
        """The highest discharge pressure this model works against."""

        return Pressure.from_psia(inlet.psia * self.max_back_pressure_percent / 100.0)

    def suits_header(self, header: SteamHeader) -> bool:
        if not self.suits_pressure(header.operating_pressure):
            return False
        limit = self.back_pressure_limit_at(header.operating_pressure)
        return header.discharge_pressure <= limit

    def is_orderable(self) -> bool:
        return not self.discontinued

    @property
    def has_warranty(self) -> bool:
        return self.warranty_months > 0

    def __str__(self) -> str:
        return f"{self.manufacturer} {self.code} ({self.orifice_diameter_in:.3f} in)"


class TrapCatalogue:
    """Every model this site buys, keyed by manufacturer and code."""

    def __init__(self, models: list[TrapModel] | None = None) -> None:
        self._models: dict[tuple[str, str], TrapModel] = {}
        for model in models or []:
            self.add(model)

    def add(self, model: TrapModel) -> None:
        if model.key in self._models:
            raise ConflictError(f"{model.manufacturer} {model.code} is already in the catalogue")
        self._models[model.key] = model

    def get(self, manufacturer: str, code: str) -> TrapModel:
        key = (manufacturer.strip().upper(), code.strip().upper())
        try:
            return self._models[key]
        except KeyError:
            raise NotFoundError("trap model", f"{manufacturer} {code}") from None

    def find(self, manufacturer: str, code: str) -> TrapModel | None:
        key = (manufacturer.strip().upper(), code.strip().upper())
        return self._models.get(key)

    def with_principle(self, principle: OperatingPrinciple) -> list[TrapModel]:
        return sorted(
            (m for m in self._models.values() if m.principle is principle),
            key=lambda m: m.key,
        )

    def orderable_for(self, header: SteamHeader) -> list[TrapModel]:
        """What could be put on this header out of current stock."""

        return sorted(
            (m for m in self._models.values() if m.is_orderable() and m.suits_header(header)),
            key=lambda m: (m.list_price.cents, m.key),
        )

    def successor_of(self, model: TrapModel) -> TrapModel | None:
        """Follow a discontinued model to whatever took its place."""

        seen: set[str] = set()
        current = model
        while current.replaced_by is not None:
            if current.code in seen:
                raise ConflictError(f"the replacement chain from {model.code} loops")
            seen.add(current.code)
            nxt = self.find(current.manufacturer, current.replaced_by)
            if nxt is None:
                return None
            current = nxt
        return None if current is model else current

    def __len__(self) -> int:
        return len(self._models)

    def __contains__(self, key: object) -> bool:
        return key in self._models

    def __iter__(self) -> Iterator[TrapModel]:
        return iter(sorted(self._models.values(), key=lambda m: m.key))
