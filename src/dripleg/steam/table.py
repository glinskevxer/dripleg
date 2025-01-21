"""The saturated steam table this package reads, and the row type it hands out.

Values are the ordinary English unit saturation table: absolute pressure in
psia, saturation temperature in F, saturated liquid and vapour enthalpy in
Btu/lb, latent heat as the difference, and saturated vapour specific volume in
cubic feet per pound.

The table is deliberately a table and not a correlation. A survey report gets
argued over by people holding a printed steam table, and a number that does not
match the book they are holding costs more credibility than the third decimal
place is worth. Everything between rows is interpolated, and everything outside
the ends raises rather than extrapolating.
"""

from __future__ import annotations

from dataclasses import dataclass

from dripleg.errors import OutOfRangeError, ValidationError
from dripleg.units.energy import SpecificEnthalpy
from dripleg.units.pressure import Pressure
from dripleg.units.temperature import Temperature

__all__ = [
    "SATURATION_TABLE",
    "TABLE_MAX_PSIA",
    "TABLE_MIN_PSIA",
    "SaturationPoint",
    "row_bracketing_pressure",
    "row_bracketing_temperature",
]


@dataclass(frozen=True)
class SaturationPoint:
    """One state on the saturation line, whether a table row or interpolated."""

    pressure: Pressure
    temperature: Temperature
    liquid_enthalpy: SpecificEnthalpy
    latent_heat: SpecificEnthalpy
    vapour_enthalpy: SpecificEnthalpy
    vapour_specific_volume: float

    def __post_init__(self) -> None:
        if self.vapour_specific_volume <= 0:
            raise ValidationError("specific volume has to be positive", field="specific_volume")
        gap = self.vapour_enthalpy.btu_per_pound - (
            self.liquid_enthalpy.btu_per_pound + self.latent_heat.btu_per_pound
        )
        if abs(gap) > 0.06:
            raise ValidationError(
                f"hf plus hfg is {gap:+.2f} Btu/lb away from hg",
                field="enthalpy",
            )

    @property
    def vapour_density(self) -> float:
        """Pounds per cubic foot, which is what a velocity check wants."""

        return 1.0 / self.vapour_specific_volume

    def sensible_heat_above(self, datum: Temperature) -> SpecificEnthalpy:
        """Heat in the condensate above a feedwater datum, roughly one Btu per
        pound per degree. Good enough for a makeup credit and no more."""

        return SpecificEnthalpy.from_btu_per_pound(
            self.liquid_enthalpy.btu_per_pound - (datum.fahrenheit - 32.0)
        )


# psia, Tsat F, hf, hfg, hg, vg
_ROWS: tuple[tuple[float, float, float, float, float, float], ...] = (
    (0.5, 79.56, 47.62, 1048.6, 1096.2, 641.5),
    (1.0, 101.74, 69.73, 1036.3, 1106.0, 333.6),
    (2.0, 126.08, 94.03, 1022.2, 1116.2, 173.73),
    (3.0, 141.48, 109.42, 1013.2, 1122.6, 118.71),
    (5.0, 162.24, 130.13, 1001.0, 1131.1, 73.53),
    (7.5, 179.94, 147.93, 990.2, 1138.1, 50.29),
    (10.0, 193.21, 161.23, 982.1, 1143.3, 38.42),
    (14.696, 212.00, 180.17, 970.3, 1150.5, 26.80),
    (20.0, 227.96, 196.27, 960.0, 1156.3, 20.09),
    (25.0, 240.07, 208.45, 952.1, 1160.6, 16.303),
    (30.0, 250.34, 218.82, 945.3, 1164.1, 13.746),
    (40.0, 267.25, 236.03, 933.8, 1169.8, 10.498),
    (50.0, 281.02, 250.21, 923.9, 1174.1, 8.515),
    (60.0, 292.71, 262.25, 915.3, 1177.6, 7.175),
    (70.0, 302.93, 272.74, 907.9, 1180.6, 6.206),
    (80.0, 312.04, 282.15, 900.9, 1183.1, 5.472),
    (90.0, 320.28, 290.69, 894.6, 1185.3, 4.896),
    (100.0, 327.82, 298.54, 888.7, 1187.2, 4.432),
    (120.0, 341.27, 312.58, 877.8, 1190.4, 3.728),
    (140.0, 353.04, 324.96, 868.0, 1193.0, 3.219),
    (160.0, 363.55, 336.11, 859.0, 1195.1, 2.834),
    (180.0, 373.08, 346.22, 850.7, 1196.9, 2.532),
    (200.0, 381.80, 355.51, 842.8, 1198.3, 2.288),
    (250.0, 401.04, 376.09, 825.0, 1201.1, 1.8438),
    (300.0, 417.35, 393.94, 809.0, 1202.9, 1.5433),
    (350.0, 431.73, 409.79, 794.1, 1203.9, 1.3260),
    (400.0, 444.60, 424.17, 780.4, 1204.6, 1.1613),
    (450.0, 456.28, 437.36, 767.4, 1204.8, 1.0320),
    (500.0, 467.01, 449.62, 755.7, 1205.3, 0.9283),
    (600.0, 486.21, 471.70, 732.4, 1204.1, 0.7702),
    (700.0, 503.10, 491.60, 710.2, 1201.8, 0.6558),
    (800.0, 518.23, 509.70, 688.9, 1198.6, 0.5691),
    (900.0, 531.98, 526.60, 668.2, 1194.8, 0.5009),
    (1000.0, 544.61, 542.40, 648.2, 1190.6, 0.4456),
)


def _point(row: tuple[float, float, float, float, float, float]) -> SaturationPoint:
    psia, tsat, hf, hfg, hg, vg = row
    return SaturationPoint(
        pressure=Pressure.from_psia(psia),
        temperature=Temperature.from_fahrenheit(tsat),
        liquid_enthalpy=SpecificEnthalpy.from_btu_per_pound(hf),
        latent_heat=SpecificEnthalpy.from_btu_per_pound(hfg),
        vapour_enthalpy=SpecificEnthalpy.from_btu_per_pound(hg),
        vapour_specific_volume=vg,
    )


SATURATION_TABLE: tuple[SaturationPoint, ...] = tuple(_point(row) for row in _ROWS)

TABLE_MIN_PSIA = _ROWS[0][0]
TABLE_MAX_PSIA = _ROWS[-1][0]


def row_bracketing_pressure(psia: float) -> tuple[SaturationPoint, SaturationPoint]:
    """The two rows a pressure sits between, or the same row twice on a hit."""

    if psia < TABLE_MIN_PSIA or psia > TABLE_MAX_PSIA:
        raise OutOfRangeError(
            f"{psia:g} psia is outside the table",
            field="pressure",
            low=TABLE_MIN_PSIA,
            high=TABLE_MAX_PSIA,
            value=psia,
        )
    lower = SATURATION_TABLE[0]
    for point in SATURATION_TABLE:
        if point.pressure.psia == psia:
            return point, point
        if point.pressure.psia > psia:
            return lower, point
        lower = point
    return lower, lower


def row_bracketing_temperature(fahrenheit: float) -> tuple[SaturationPoint, SaturationPoint]:
    """The same walk down the temperature column, for the inverse lookup."""

    low = SATURATION_TABLE[0].temperature.fahrenheit
    high = SATURATION_TABLE[-1].temperature.fahrenheit
    if fahrenheit < low or fahrenheit > high:
        raise OutOfRangeError(
            f"{fahrenheit:g} F is outside the table",
            field="temperature",
            low=low,
            high=high,
            value=fahrenheit,
        )
    lower = SATURATION_TABLE[0]
    for point in SATURATION_TABLE:
        if point.temperature.fahrenheit == fahrenheit:
            return point, point
        if point.temperature.fahrenheit > fahrenheit:
            return lower, point
        lower = point
    return lower, lower
