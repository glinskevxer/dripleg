"""Running the sizing check across a register, and saying what it cannot check.

Most stations will not have the geometry on them. The drawing office knows the
pipe size and the run length, the survey contractor does not, and the register
gets built from the survey. So the audit reports two populations: the stations
it could size, and the stations it could not, with the second one named rather
than quietly left out. A sizing audit covering eleven percent of the register
and not saying so is worse than no audit.

The load a drip station has to clear is the warm up load, not the running one,
so that is what the check is run against. On process service neither figure is
knowable from the register, so those are skipped and said to be skipped.
"""

from __future__ import annotations

from dataclasses import dataclass

from dripleg.model.attributes import ServiceType
from dripleg.model.installation import TrapInstallation
from dripleg.model.register import TrapRegister
from dripleg.model.tags import TrapTag
from dripleg.sizing.capacity import SizingCheck, SizingVerdict, check_sizing
from dripleg.sizing.load import pipe_size, running_load, warmup_load
from dripleg.steam.saturated import at_pressure
from dripleg.units.temperature import Temperature

__all__ = ["SizingAudit", "SizingRow", "audit_sizing"]

DEFAULT_COLD = Temperature.from_fahrenheit(60.0)
DEFAULT_AMBIENT = Temperature.from_fahrenheit(75.0)

# Only these services have a load this package can work out from the register.
SIZEABLE = frozenset({ServiceType.DRIP, ServiceType.SEPARATOR})


@dataclass(frozen=True)
class SizingRow:
    """One station that could be sized."""

    station: TrapInstallation
    check: SizingCheck
    warmup_pph: float
    running_pph: float

    @property
    def tag(self) -> TrapTag:
        return self.station.tag

    @property
    def verdict(self) -> SizingVerdict:
        return self.check.verdict

    def __str__(self) -> str:
        return f"{self.tag} {self.verdict.label}: {self.check.note}"


@dataclass(frozen=True)
class SizingAudit:
    """What the sizing check made of a register."""

    rows: list[SizingRow]
    no_geometry: list[TrapTag]
    not_sizeable: list[TrapTag]

    @property
    def checked(self) -> int:
        return len(self.rows)

    @property
    def skipped(self) -> int:
        return len(self.no_geometry) + len(self.not_sizeable)

    @property
    def coverage(self) -> float:
        total = self.checked + self.skipped
        if total == 0:
            return 0.0
        return self.checked / total

    def in_verdict(self, verdict: SizingVerdict) -> list[SizingRow]:
        return [row for row in self.rows if row.verdict is verdict]

    def counts(self) -> dict[str, int]:
        return {verdict.label: len(self.in_verdict(verdict)) for verdict in SizingVerdict}

    @property
    def wrong(self) -> list[SizingRow]:
        """Everything that is not correctly sized, worst ratio first."""

        bad = [row for row in self.rows if row.verdict.needs_attention]
        return sorted(bad, key=lambda row: (row.check.ratio, str(row.tag)))

    def __str__(self) -> str:
        counts = self.counts()
        return (
            f"{self.checked} sized, {self.skipped} skipped: "
            f"{counts['undersized']} undersized, {counts['oversized']} oversized"
        )


def audit_sizing(
    register: TrapRegister,
    *,
    cold: Temperature = DEFAULT_COLD,
    ambient: Temperature = DEFAULT_AMBIENT,
) -> SizingAudit:
    """Size every station that carries enough to be sized."""

    rows: list[SizingRow] = []
    no_geometry: list[TrapTag] = []
    not_sizeable: list[TrapTag] = []
    for station in register:
        if station.service not in SIZEABLE:
            not_sizeable.append(station.tag)
            continue
        if not station.has_geometry:
            no_geometry.append(station.tag)
            continue
        assert station.pipe_nominal is not None
        assert station.run_length_ft is not None
        pipe = pipe_size(station.pipe_nominal)
        pressure = station.header.operating_pressure
        warm = warmup_load(
            pipe,
            station.run_length_ft,
            pressure,
            cold,
            minutes=station.warmup_minutes,
        )
        running = running_load(
            pipe,
            station.run_length_ft,
            pressure,
            ambient,
            insulated=station.insulated,
        )
        rows.append(
            SizingRow(
                station=station,
                check=check_sizing(
                    station.model,
                    warm,
                    station.header.differential_pressure,
                    at_pressure(pressure).temperature,
                ),
                warmup_pph=warm.pounds_per_hour,
                running_pph=running.pounds_per_hour,
            )
        )
    return SizingAudit(rows=rows, no_geometry=no_geometry, not_sizeable=not_sizeable)
