"""Build a small plant in memory and walk it end to end.

This is the check that the installed wheel actually works, and it is
deliberately not a test. It imports nothing from the test suite, it writes no
files, and it runs against whatever is on the path, so CI can install the built
wheel into a clean environment and run this to find out whether the package is
importable and coherent rather than whether the source tree is.

It has caught two things the unit tests could not: a module left out of the
wheel because the packaging config listed packages by hand, and a data file
that was only on disk because the tests happened to run from the source tree.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from dripleg.diagnosis.batch import diagnose_survey
from dripleg.loss.register import build_loss_register
from dripleg.model.attributes import Accessibility, Criticality, ServiceType
from dripleg.model.catalogue import ConnectionType, TrapCatalogue, TrapModel
from dripleg.model.header import SteamHeader
from dripleg.model.installation import TrapInstallation
from dripleg.model.operating import OperatingProfile
from dripleg.model.plant import Area, Site
from dripleg.model.principles import OperatingPrinciple
from dripleg.model.register import TrapRegister
from dripleg.model.tags import SiteCode, TrapTag
from dripleg.repair.priority import WorkList, rank_jobs
from dripleg.repair.recommend import recommend
from dripleg.report.loss_report import build_loss_report
from dripleg.store.basis_repo import BasisRepository, SiteBasis
from dripleg.store.db import Database
from dripleg.store.migrations import migrate
from dripleg.store.plant_repo import PlantRepository
from dripleg.survey.condition import TrapCondition
from dripleg.survey.observation import Observation
from dripleg.survey.readings import TemperatureReading, UltrasonicReading
from dripleg.survey.survey import Survey
from dripleg.units.money import Money
from dripleg.units.pressure import Pressure
from dripleg.units.temperature import Temperature

__all__ = ["build_plant", "main", "walk"]

DAY = dt.date(2025, 4, 8)
AREA = Area.of("SMK1", "A1", "Smoke test area", "CC1")
MODEL = TrapModel(
    manufacturer="Halden",
    code="TD52",
    principle=OperatingPrinciple.THERMODYNAMIC_DISC,
    orifice_diameter_in=0.093,
    max_operating_pressure=Pressure.from_psig(600.0),
    max_back_pressure_percent=80.0,
    connection_size_in=0.5,
    connection_type=ConnectionType.SCREWED,
    list_price=Money.from_dollars("184.00"),
)


def build_plant() -> tuple[TrapRegister, TrapCatalogue]:
    """Two traps on one header: one blowing, one healthy."""

    header = SteamHeader.of(AREA, "MP", "Smoke main", 125.0, discharge_psig=15.0)
    register = TrapRegister(
        TrapInstallation(
            site=SiteCode("SMK1"),
            tag=TrapTag.of("A1", "MP", sequence),
            header=header,
            model=MODEL,
            service=ServiceType.DRIP,
            accessibility=Accessibility.GROUND_LEVEL,
            criticality=Criticality.NUISANCE,
            profile=OperatingProfile.continuous(),
            installed_on=dt.date(2021, 6, 14),
        )
        for sequence in (1, 2)
    )
    return register, TrapCatalogue([MODEL])


def _reading(sequence: int, blowing: bool) -> Observation:
    return Observation(
        tag=TrapTag.of("A1", "MP", sequence),
        observed_on=DAY,
        technician="smoke test",
        reported_condition=TrapCondition.OK,
        ultrasonic=UltrasonicReading(
            decibels=70.0 if blowing else 32.0, seconds=30.0, cycles=0 if blowing else 2
        ),
        temperature=TemperatureReading(
            upstream=Temperature.from_fahrenheit(345.0 if blowing else 350.0),
            downstream=Temperature.from_fahrenheit(258.0 if blowing else 200.0),
        ),
    )


def walk() -> dict[str, object]:
    """Run the whole chain and hand back what it produced."""

    register, catalogue = build_plant()
    survey = Survey("SMK1", "SMOKE-1", "Smoke", "in house", DAY - dt.timedelta(days=1))
    survey.record(_reading(1, blowing=True))
    survey.record(_reading(2, blowing=False))
    survey.close(DAY)
    basis = SiteBasis.typical()
    diagnosis = diagnose_survey(register, survey)
    losses = build_loss_register(register, diagnosis, basis.energy, basis.costs, basis.factor)
    work = WorkList(
        rank_jobs([(row, recommend(row, basis.repairs, catalogue)) for row in losses.rows])
    )
    with Database() as book:
        migrate(book)
        plant = PlantRepository(book)
        plant.save_site(Site.of("SMK1", "Smoke test plant", "in house"))
        plant.save_area(AREA)
        BasisRepository(book).save("SMK1", basis)
        tables = len(book.table_names())
    report = build_loss_report(losses)
    return {
        "traps": len(register),
        "failures": len(diagnosis.failures()),
        "losing": len(losses.losing),
        "annual_cost": str(losses.total_cost),
        "jobs": len(work.actionable),
        "tables": tables,
        "report_lines": len(report.lines()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Walk the package end to end.")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    facts = walk()
    problems: list[str] = []
    if facts["traps"] != 2:
        problems.append("the smoke plant did not build")
    if facts["failures"] != 1:
        problems.append("the diagnosis engine did not find the blowing trap")
    if facts["losing"] != 1:
        problems.append("the loss engine did not cost the blowing trap")
    if facts["jobs"] != 1:
        problems.append("the repair engine did not raise a job")
    if int(str(facts["tables"])) < 10:
        problems.append("the migrations did not build the schema")
    if problems:
        for line in problems:
            print(line, file=sys.stderr)
        return 1
    if not args.quiet:
        for key, value in facts.items():
            print(f"{key.replace('_', ' ')}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
