"""Reading a survey export into observations, and quarantining what will not go.

The rule this module exists to enforce: one bad row does not lose the file. A
technician who typed a tag wrong on line 40 of a 300 line export should cost
the office one correction, not a re-import of the whole survey, and certainly
not a silent drop.

So every row that cannot be read lands in quarantine with the line number, the
raw values and the reason, and the caller decides what to do about it. Nothing
is skipped quietly and nothing is guessed.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
from dataclasses import dataclass, field

from dripleg.errors import DriplegError, ValidationError
from dripleg.ingest.profile import MappingProfile, profile_for_header
from dripleg.model.tags import TrapTag
from dripleg.survey.condition import TrapCondition
from dripleg.survey.observation import Observation
from dripleg.survey.readings import (
    SightGlassView,
    SurveyMethod,
    TemperatureReading,
    UltrasonicReading,
)
from dripleg.units.pressure import Pressure
from dripleg.units.temperature import Temperature

__all__ = ["ImportResult", "QuarantinedRow", "read_survey_csv"]

_DATE_ORDERS = {
    "ymd": ("%Y-%m-%d", "%Y/%m/%d"),
    "dmy": ("%d/%m/%Y", "%d-%m-%Y"),
    "mdy": ("%m/%d/%Y", "%m-%d-%Y"),
}


@dataclass(frozen=True)
class QuarantinedRow:
    """A row that could not be read, and why."""

    line: int
    reason: str
    values: dict[str, str] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"line {self.line}: {self.reason}"


@dataclass(frozen=True)
class ImportResult:
    """What came out of one file."""

    profile: MappingProfile
    observations: list[Observation]
    quarantined: list[QuarantinedRow]
    content_hash: str

    @property
    def read(self) -> int:
        return len(self.observations)

    @property
    def rejected(self) -> int:
        return len(self.quarantined)

    @property
    def total_rows(self) -> int:
        return self.read + self.rejected

    @property
    def is_clean(self) -> bool:
        return not self.quarantined

    @property
    def acceptance_rate(self) -> float:
        if self.total_rows == 0:
            return 0.0
        return self.read / self.total_rows

    def __str__(self) -> str:
        return (
            f"{self.profile.name}: {self.read} read, {self.rejected} quarantined "
            f"({self.content_hash[:8]})"
        )


def _text(row: dict[str, str], profile: MappingProfile, name: str) -> str:
    column = profile.column_for(name)
    if column is None:
        return ""
    for key, value in row.items():
        if key is not None and key.strip().lower() == column.lower():
            return (value or "").strip()
    return ""


def _number(row: dict[str, str], profile: MappingProfile, name: str) -> float | None:
    raw = _text(row, profile, name)
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        raise ValidationError(f"{raw!r} in the {name} column is not a number", field=name) from None


def _date(raw: str, order: str) -> dt.date:
    if not raw:
        raise ValidationError("the row has no date on it", field="observed_on")
    for pattern in _DATE_ORDERS[order]:
        try:
            return dt.datetime.strptime(raw, pattern).date()
        except ValueError:
            continue
    raise ValidationError(
        f"{raw!r} is not a {order} date, which is what this profile exports",
        field="observed_on",
    )


def _temperature(value: float, unit: str) -> Temperature:
    if unit.upper() == "C":
        return Temperature.from_celsius(value)
    return Temperature.from_fahrenheit(value)


def _sound(row: dict[str, str], profile: MappingProfile) -> UltrasonicReading | None:
    decibels = _number(row, profile, "decibels")
    if decibels is None:
        return None
    seconds = _number(row, profile, "probe_seconds") or profile.probe_seconds_default
    cycles = _number(row, profile, "cycles")
    return UltrasonicReading(
        decibels=decibels,
        seconds=seconds,
        cycles=None if cycles is None else int(cycles),
    )


def _heat(row: dict[str, str], profile: MappingProfile) -> TemperatureReading | None:
    upstream = _number(row, profile, "upstream")
    downstream = _number(row, profile, "downstream")
    if upstream is None or downstream is None:
        if upstream is not None or downstream is not None:
            raise ValidationError("only one side of the trap was recorded", field="temperature")
        return None
    ambient = _number(row, profile, "ambient")
    unit = profile.temperature_unit
    return TemperatureReading(
        upstream=_temperature(upstream, unit),
        downstream=_temperature(downstream, unit),
        ambient=None if ambient is None else _temperature(ambient, unit),
        method=SurveyMethod.CONTACT_TEMPERATURE,
    )


def _row_to_observation(row: dict[str, str], profile: MappingProfile) -> Observation:
    tag = TrapTag.parse(_text(row, profile, "tag"))
    observed_on = _date(_text(row, profile, "observed_on"), profile.date_order)
    condition = TrapCondition.parse(_text(row, profile, "condition"))
    glass_text = _text(row, profile, "sight_glass")
    pressure_value = _number(row, profile, "pressure")
    photo = _text(row, profile, "photo")
    return Observation(
        tag=tag,
        observed_on=observed_on,
        technician=_text(row, profile, "technician"),
        reported_condition=condition,
        ultrasonic=_sound(row, profile),
        temperature=_heat(row, profile),
        sight_glass=None if not glass_text else _sight_glass(glass_text),
        measured_pressure=None
        if pressure_value is None
        else Pressure.of(pressure_value, profile.pressure_unit),
        note=_text(row, profile, "note"),
        photo_reference=photo or None,
    )


def _sight_glass(text: str) -> SightGlassView:
    cleaned = text.strip().lower().replace(" ", "_")
    for member in SightGlassView:
        if member.value == cleaned:
            return member
    raise ValidationError(f"{text!r} is not a sight glass reading", field="sight_glass")


def read_survey_csv(text: str, profile: MappingProfile | None = None) -> ImportResult:
    """Read an export into observations, quarantining the rows that will not go."""

    reader = csv.DictReader(io.StringIO(text))
    header = list(reader.fieldnames or [])
    if not header:
        raise DriplegError("the file has no header row")
    chosen = profile if profile is not None else profile_for_header(header)
    if not chosen.matches(header):
        missing = ", ".join(chosen.missing_from(header))
        raise ValidationError(
            f"profile {chosen.name} needs columns this file does not have: {missing}",
            field="profile",
        )
    observations: list[Observation] = []
    quarantined: list[QuarantinedRow] = []
    seen: set[TrapTag] = set()
    for line, row in enumerate(reader, start=2):
        cleaned = {k: (v or "") for k, v in row.items() if k is not None}
        try:
            observation = _row_to_observation(cleaned, chosen)
        except (ValidationError, ValueError) as problem:
            quarantined.append(QuarantinedRow(line=line, reason=str(problem), values=cleaned))
            continue
        if observation.tag in seen:
            quarantined.append(
                QuarantinedRow(
                    line=line,
                    reason=f"{observation.tag} appears twice in this file",
                    values=cleaned,
                )
            )
            continue
        seen.add(observation.tag)
        observations.append(observation)
    return ImportResult(
        profile=chosen,
        observations=observations,
        quarantined=quarantined,
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )
