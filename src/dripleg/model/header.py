"""Steam headers, and the pressure a trap discharges against.

Two pressures decide almost everything about a trap. The header pressure sets
the saturation temperature the technician expects to read upstream and the
driving pressure in the loss calculation. The discharge pressure sets what the
trap is pushing against, and if it is high enough relative to the header the
flow through a failed seat stops being choked, which changes the loss by a
third and changes the diagnosis entirely.

So a header owns both, and refuses to be built with a discharge pressure above
the steam pressure, which is a data entry error and not a plant.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from dripleg.errors import ValidationError
from dripleg.model.plant import Area
from dripleg.model.tags import AreaCode, SiteCode, SystemCode
from dripleg.steam.saturated import at_pressure
from dripleg.units.pressure import Pressure
from dripleg.units.temperature import Temperature

__all__ = ["DischargeDestination", "PressureClass", "SteamHeader"]

# Where the pressure class boundaries sit, in psig. These are the ones the
# insurance schedule uses at this site, not a law of nature.
_MEDIUM_FLOOR_PSIG = 16.0
_HIGH_FLOOR_PSIG = 150.0

# A gauge pressure comes back out of an absolute store a whisker short of the
# number that went in, and a boundary read exactly is a boundary read wrong.
_BOUNDARY_SLACK_PSI = 1e-6


class PressureClass(Enum):
    VACUUM = "vacuum"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def label(self) -> str:
        return {
            PressureClass.VACUUM: "vacuum",
            PressureClass.LOW: "LP",
            PressureClass.MEDIUM: "MP",
            PressureClass.HIGH: "HP",
        }[self]

    @classmethod
    def of(cls, pressure: Pressure) -> PressureClass:
        if pressure.is_vacuum:
            return cls.VACUUM
        if pressure.psig >= _HIGH_FLOOR_PSIG - _BOUNDARY_SLACK_PSI:
            return cls.HIGH
        if pressure.psig >= _MEDIUM_FLOOR_PSIG - _BOUNDARY_SLACK_PSI:
            return cls.MEDIUM
        return cls.LOW


class DischargeDestination(Enum):
    """Where what comes out of the trap goes."""

    RETURN_LINE = "return"
    ATMOSPHERE = "atmosphere"
    DRAIN = "drain"
    FLASH_VESSEL = "flash_vessel"

    @property
    def condensate_is_recovered(self) -> bool:
        return self in {DischargeDestination.RETURN_LINE, DischargeDestination.FLASH_VESSEL}

    @property
    def steam_is_visible(self) -> bool:
        """Whether a failed trap on this destination shows itself to the eye.

        A trap blowing to atmosphere plumes and somebody reports it. A trap
        blowing into a closed return does not, which is why the closed ones are
        where the money is.
        """

        return self is DischargeDestination.ATMOSPHERE


@dataclass(frozen=True)
class SteamHeader:
    """A steam main or branch, at one pressure, feeding a set of traps."""

    site: SiteCode
    area: AreaCode
    system: SystemCode
    name: str
    operating_pressure: Pressure
    design_pressure: Pressure
    discharge_pressure: Pressure
    destination: DischargeDestination = DischargeDestination.RETURN_LINE

    def __post_init__(self) -> None:
        cleaned = " ".join(self.name.split())
        if not cleaned:
            raise ValidationError("a header needs a name", field="name")
        object.__setattr__(self, "name", cleaned)
        if self.design_pressure < self.operating_pressure:
            raise ValidationError(
                "a header cannot run above its design pressure",
                field="design_pressure",
            )
        if self.discharge_pressure > self.operating_pressure:
            raise ValidationError(
                "the discharge pressure is above the steam pressure, which is backwards",
                field="discharge_pressure",
            )
        if (
            self.destination is DischargeDestination.ATMOSPHERE
            and self.discharge_pressure.is_vacuum
        ):
            raise ValidationError(
                "a trap discharging to atmosphere is not discharging into a vacuum",
                field="discharge_pressure",
            )

    @classmethod
    def of(
        cls,
        area: Area,
        system: str,
        name: str,
        operating_psig: float,
        *,
        design_psig: float | None = None,
        discharge_psig: float = 0.0,
        destination: DischargeDestination = DischargeDestination.RETURN_LINE,
    ) -> SteamHeader:
        operating = Pressure.from_psig(operating_psig)
        design = Pressure.from_psig(
            design_psig if design_psig is not None else operating_psig * 1.2
        )
        return cls(
            site=area.site,
            area=area.code,
            system=SystemCode.parse(system),
            name=name,
            operating_pressure=operating,
            design_pressure=design,
            discharge_pressure=Pressure.from_psig(discharge_psig),
            destination=destination,
        )

    @property
    def pressure_class(self) -> PressureClass:
        return PressureClass.of(self.operating_pressure)

    @property
    def saturation_temperature(self) -> Temperature:
        return at_pressure(self.operating_pressure).temperature

    @property
    def differential_pressure(self) -> Pressure:
        """What the trap has to push against, as a differential in psi."""

        return Pressure.from_psia(self.operating_pressure.psia - self.discharge_pressure.psia)

    @property
    def back_pressure_ratio(self) -> float:
        return self.discharge_pressure.ratio_to(self.operating_pressure)

    @property
    def discharge_is_choked(self) -> bool:
        """Critical flow through the seat, which is the usual case.

        Below the critical ratio the leak rate stops caring about downstream
        pressure at all, which is what makes Napier usable in the field.
        """

        return self.back_pressure_ratio <= 0.577

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.site.value, self.area.value, self.system.value)

    def __str__(self) -> str:
        return f"{self.area}-{self.system} {self.name} at {self.operating_pressure}"
