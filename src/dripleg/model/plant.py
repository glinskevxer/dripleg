"""Sites and areas: where a trap is, in the terms the plant uses for itself.

An area is not a geographic box, it is whatever the plant calls a piece of
itself for the purpose of charging money to it. That matters because a loss
report is only acted on once it lands on a cost centre with a budget, so the
area carries the cost centre and the survey rolls up through it.
"""

from __future__ import annotations

from dataclasses import dataclass

from dripleg.errors import ValidationError
from dripleg.model.tags import AreaCode, SiteCode

__all__ = ["Area", "Site"]

MAX_NAME = 80


def _name(value: str, field: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValidationError(f"{field} cannot be blank", field=field)
    if len(cleaned) > MAX_NAME:
        raise ValidationError(f"{field} is longer than {MAX_NAME} characters", field=field)
    return cleaned


@dataclass(frozen=True)
class Site:
    """A plant. Surveys, tags and prices all belong to exactly one."""

    code: SiteCode
    name: str
    operator: str
    programme_start_month: int = 1
    fuel_price_basis: str = "delivered natural gas"

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _name(self.name, "name"))
        object.__setattr__(self, "operator", _name(self.operator, "operator"))
        if not 1 <= self.programme_start_month <= 12:
            raise ValidationError(
                f"the programme year starts in a month, got {self.programme_start_month}",
                field="programme_start_month",
            )
        if not self.fuel_price_basis.strip():
            raise ValidationError("say what the fuel price is for", field="fuel_price_basis")

    @classmethod
    def of(
        cls,
        code: str,
        name: str,
        operator: str,
        *,
        programme_start_month: int = 1,
        fuel_price_basis: str = "delivered natural gas",
    ) -> Site:
        return cls(
            code=SiteCode.parse(code),
            name=name,
            operator=operator,
            programme_start_month=programme_start_month,
            fuel_price_basis=fuel_price_basis,
        )

    @property
    def runs_a_calendar_programme(self) -> bool:
        return self.programme_start_month == 1

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


@dataclass(frozen=True)
class Area:
    """A unit, block or building inside a site."""

    site: SiteCode
    code: AreaCode
    name: str
    cost_centre: str
    parent: AreaCode | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _name(self.name, "name"))
        cleaned = self.cost_centre.strip().upper()
        if not cleaned:
            raise ValidationError("an area needs a cost centre", field="cost_centre")
        object.__setattr__(self, "cost_centre", cleaned)
        if self.parent is not None and self.parent == self.code:
            raise ValidationError("an area cannot be its own parent", field="parent")

    @classmethod
    def of(
        cls,
        site: str,
        code: str,
        name: str,
        cost_centre: str,
        *,
        parent: str | None = None,
    ) -> Area:
        return cls(
            site=SiteCode.parse(site),
            code=AreaCode.parse(code),
            name=name,
            cost_centre=cost_centre,
            parent=AreaCode.parse(parent) if parent is not None else None,
        )

    @property
    def is_top_level(self) -> bool:
        return self.parent is None

    def belongs_to(self, site: Site) -> bool:
        return self.site == site.code

    @property
    def key(self) -> tuple[str, str]:
        return (self.site.value, self.code.value)

    def __str__(self) -> str:
        return f"{self.site}/{self.code} {self.name}"
