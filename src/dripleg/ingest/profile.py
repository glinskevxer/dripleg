"""Column mapping profiles, one per tool that exports a survey.

Three tablets are in use across the sites this runs at and none of them agrees
with another about anything. One writes `TrapID`, one writes `Asset Number` and
one writes `tag`. One puts temperatures in Celsius without saying so. One
exports the date as `04/08/2025`, which is April in one hemisphere and August
in the other and is the single most expensive ambiguity in this whole package.

The answer is not a clever column sniffer. A sniffer that guesses right ninety
percent of the time is worse than no sniffer, because the tenth file is wrong
in a way nobody notices. So a profile is written down per tool, it declares its
date order explicitly, and a file whose header does not match a profile is
refused rather than guessed at.
"""

from __future__ import annotations

from dataclasses import dataclass

from dripleg.errors import ValidationError

__all__ = [
    "MappingProfile",
    "PROFILES",
    "profile_for_header",
    "profile_named",
]

REQUIRED_FIELDS = frozenset({"tag", "observed_on", "technician", "condition"})

OPTIONAL_FIELDS = frozenset(
    {
        "decibels",
        "probe_seconds",
        "cycles",
        "upstream",
        "downstream",
        "ambient",
        "sight_glass",
        "pressure",
        "note",
        "photo",
    }
)


@dataclass(frozen=True)
class MappingProfile:
    """How one tool's export lines up with the fields this package wants."""

    name: str
    columns: dict[str, str]
    date_order: str = "ymd"
    temperature_unit: str = "F"
    pressure_unit: str = "psig"
    probe_seconds_default: float = 30.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValidationError("a mapping profile needs a name", field="name")
        missing = REQUIRED_FIELDS - set(self.columns)
        if missing:
            raise ValidationError(
                f"profile {self.name} does not map {', '.join(sorted(missing))}",
                field="columns",
            )
        unknown = set(self.columns) - REQUIRED_FIELDS - OPTIONAL_FIELDS
        if unknown:
            raise ValidationError(
                f"profile {self.name} maps fields this build does not know: "
                f"{', '.join(sorted(unknown))}",
                field="columns",
            )
        if self.date_order not in {"ymd", "dmy", "mdy"}:
            raise ValidationError(
                "a date order is ymd, dmy or mdy, and it has to be stated",
                field="date_order",
            )
        if self.temperature_unit.upper() not in {"F", "C"}:
            raise ValidationError("temperatures are exported in F or C", field="temperature_unit")
        if self.probe_seconds_default <= 0:
            raise ValidationError(
                "a default probe window is positive", field="probe_seconds_default"
            )
        lowered = [name.strip().lower() for name in self.columns.values()]
        if len(set(lowered)) != len(lowered):
            raise ValidationError(
                f"profile {self.name} points two fields at the same column",
                field="columns",
            )

    @property
    def required_columns(self) -> list[str]:
        return sorted(self.columns[name] for name in REQUIRED_FIELDS)

    def column_for(self, field_name: str) -> str | None:
        return self.columns.get(field_name)

    def has(self, field_name: str) -> bool:
        return field_name in self.columns

    def matches(self, header: list[str]) -> bool:
        """Whether a file's header carries every column this profile needs."""

        present = {name.strip().lower() for name in header}
        return all(column.lower() in present for column in self.required_columns)

    def missing_from(self, header: list[str]) -> list[str]:
        present = {name.strip().lower() for name in header}
        return sorted(c for c in self.required_columns if c.lower() not in present)

    def __str__(self) -> str:
        return f"{self.name} ({len(self.columns)} columns, dates {self.date_order})"


PROFILES: dict[str, MappingProfile] = {
    "ultraprobe": MappingProfile(
        name="ultraprobe",
        columns={
            "tag": "TrapID",
            "observed_on": "SurveyDate",
            "technician": "Inspector",
            "condition": "Result",
            "decibels": "dB",
            "probe_seconds": "Duration",
            "cycles": "Cycles",
            "upstream": "TempIn",
            "downstream": "TempOut",
            "note": "Comments",
        },
        date_order="ymd",
    ),
    "steamscope": MappingProfile(
        name="steamscope",
        columns={
            "tag": "Asset Number",
            "observed_on": "Date",
            "technician": "Tech",
            "condition": "Status",
            "decibels": "Ultrasound",
            "upstream": "Inlet C",
            "downstream": "Outlet C",
            "ambient": "Ambient C",
            "pressure": "Line bar",
            "note": "Note",
            "photo": "Photo",
        },
        date_order="dmy",
        temperature_unit="C",
        pressure_unit="barg",
    ),
    "fieldbook": MappingProfile(
        name="fieldbook",
        columns={
            "tag": "tag",
            "observed_on": "date",
            "technician": "by",
            "condition": "condition",
            "decibels": "db",
            "probe_seconds": "seconds",
            "cycles": "cycles",
            "upstream": "up_f",
            "downstream": "down_f",
            "ambient": "amb_f",
            "sight_glass": "glass",
            "pressure": "psig",
            "note": "note",
        },
        date_order="ymd",
    ),
}


def profile_named(name: str) -> MappingProfile:
    key = "".join(ch for ch in name.lower() if ch.isalnum())
    try:
        return PROFILES[key]
    except KeyError:
        known = ", ".join(sorted(PROFILES))
        raise ValidationError(
            f"{name!r} is not a mapping profile, expected one of: {known}",
            field="profile",
        ) from None


def profile_for_header(header: list[str]) -> MappingProfile:
    """The one profile whose columns are all present, or an error naming why.

    Deliberately refuses when two profiles match, rather than picking the first.
    Two matching profiles means a column set nobody wrote down and a file that
    should be looked at by a person.
    """

    matches = [profile for profile in PROFILES.values() if profile.matches(header)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        gaps = {p.name: p.missing_from(header) for p in PROFILES.values()}
        detail = "; ".join(f"{name} wants {', '.join(missing)}" for name, missing in gaps.items())
        raise ValidationError(f"no mapping profile fits this header: {detail}", field="profile")
    names = ", ".join(sorted(p.name for p in matches))
    raise ValidationError(
        f"this header fits more than one profile ({names}), so name one",
        field="profile",
    )
