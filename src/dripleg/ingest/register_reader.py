"""Reading an asset register export into trap stations.

A survey contractor arriving at a new plant is handed a spreadsheet, and the
spreadsheet is the drawing office's, which means it has four thousand rows, a
merged header, and a column called `Type` that holds three different things.

The rule here is the same as for survey readings: a row that cannot be read
lands in quarantine with its line number, and the rest of the file goes in.
A register import that refuses the whole file over eleven bad rows is a
register import nobody uses, and the register then lives in the spreadsheet
forever.

Unlike a survey row, a station row points at four other records: a header, a
model, a profile and an area. Those have to exist first, and a row naming one
that does not is quarantined rather than creating it, because a typo that
silently creates a header is worse than a typo that stops.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
from dataclasses import dataclass

from dripleg.errors import DriplegError, NotFoundError, ValidationError
from dripleg.ingest.reader import QuarantinedRow
from dripleg.model.attributes import Accessibility, Criticality, ServiceType
from dripleg.model.catalogue import TrapCatalogue
from dripleg.model.header import DischargeDestination, SteamHeader
from dripleg.model.installation import TrapInstallation
from dripleg.model.operating import OperatingProfile
from dripleg.model.tags import SiteCode, TrapTag

__all__ = ["RegisterImport", "read_register_csv"]

REQUIRED_COLUMNS = ("tag", "manufacturer", "model", "installed")

OPTIONAL_COLUMNS = (
    "service",
    "access",
    "criticality",
    "profile",
    "destination",
    "strainer",
    "valves",
    "interval",
    "note",
)

_TRUE = {"y", "yes", "true", "1", "t"}
_FALSE = {"n", "no", "false", "0", "f"}


@dataclass(frozen=True)
class RegisterImport:
    """What came out of an asset register file."""

    stations: list[TrapInstallation]
    quarantined: list[QuarantinedRow]
    content_hash: str

    @property
    def read(self) -> int:
        return len(self.stations)

    @property
    def rejected(self) -> int:
        return len(self.quarantined)

    @property
    def is_clean(self) -> bool:
        return not self.quarantined

    def __str__(self) -> str:
        return f"{self.read} stations read, {self.rejected} quarantined"


def _flag(text: str, default: bool) -> bool:
    cleaned = text.strip().lower()
    if not cleaned:
        return default
    if cleaned in _TRUE:
        return True
    if cleaned in _FALSE:
        return False
    raise ValidationError(f"{text!r} is not a yes or a no", field="flag")


def _enum_column(kind: type, text: str, default: object, field: str) -> object:
    cleaned = text.strip().lower().replace(" ", "_").replace("-", "_")
    if not cleaned:
        return default
    for member in kind:  # type: ignore[attr-defined]
        if member.value == cleaned:
            return member
    raise ValidationError(f"{text!r} is not a {field}", field=field)


def _row_to_station(
    row: dict[str, str],
    site: SiteCode,
    headers: dict[tuple[str, str], SteamHeader],
    catalogue: TrapCatalogue,
    profiles: dict[str, OperatingProfile],
) -> TrapInstallation:
    tag = TrapTag.parse(row.get("tag", ""))
    key = (tag.area.value, tag.system.value)
    header = headers.get(key)
    if header is None:
        raise NotFoundError("header", f"{tag.area}-{tag.system}")
    model = catalogue.find(row.get("manufacturer", ""), row.get("model", ""))
    if model is None:
        raise NotFoundError("trap model", f"{row.get('manufacturer')} {row.get('model')}")
    profile_code = (row.get("profile") or "CONT").strip()
    profile = profiles.get(profile_code)
    if profile is None:
        raise NotFoundError("operating profile", profile_code)
    interval = (row.get("interval") or "").strip()
    return TrapInstallation(
        site=site,
        tag=tag,
        header=header,
        model=model,
        service=_enum_column(ServiceType, row.get("service", ""), ServiceType.DRIP, "service"),  # type: ignore[arg-type]
        accessibility=_enum_column(  # type: ignore[arg-type]
            Accessibility, row.get("access", ""), Accessibility.GROUND_LEVEL, "access grade"
        ),
        criticality=_enum_column(  # type: ignore[arg-type]
            Criticality, row.get("criticality", ""), Criticality.NUISANCE, "criticality"
        ),
        profile=profile,
        installed_on=dt.date.fromisoformat((row.get("installed") or "").strip()),
        destination=_enum_column(  # type: ignore[arg-type]
            DischargeDestination, row.get("destination", ""), None, "discharge destination"
        ),
        strainer_fitted=_flag(row.get("strainer", ""), True),
        isolation_valves=int((row.get("valves") or "2").strip() or 2),
        interval_months_override=int(interval) if interval else None,
        note=(row.get("note") or "").strip(),
    )


def read_register_csv(
    text: str,
    site: SiteCode | str,
    headers: list[SteamHeader],
    catalogue: TrapCatalogue,
    profiles: list[OperatingProfile],
) -> RegisterImport:
    """Read an asset register export against what the book already holds."""

    reader = csv.DictReader(io.StringIO(text))
    header_row = [name.strip().lower() for name in (reader.fieldnames or [])]
    if not header_row:
        raise DriplegError("the file has no header row")
    missing = [name for name in REQUIRED_COLUMNS if name not in header_row]
    if missing:
        raise ValidationError(
            f"an asset register needs columns this file does not have: {', '.join(missing)}",
            field="columns",
        )
    site_code = site if isinstance(site, SiteCode) else SiteCode.parse(site)
    by_key = {(h.area.value, h.system.value): h for h in headers}
    by_code = {p.code: p for p in profiles}
    stations: list[TrapInstallation] = []
    quarantined: list[QuarantinedRow] = []
    seen: set[TrapTag] = set()
    for line, raw in enumerate(reader, start=2):
        row = {
            (key or "").strip().lower(): (value or "").strip()
            for key, value in raw.items()
            if key is not None
        }
        try:
            station = _row_to_station(row, site_code, by_key, catalogue, by_code)
        except (DriplegError, ValueError) as problem:
            quarantined.append(QuarantinedRow(line=line, reason=str(problem), values=row))
            continue
        if station.tag in seen:
            quarantined.append(
                QuarantinedRow(
                    line=line, reason=f"{station.tag} appears twice in this file", values=row
                )
            )
            continue
        seen.add(station.tag)
        stations.append(station)
    return RegisterImport(
        stations=stations,
        quarantined=quarantined,
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )
