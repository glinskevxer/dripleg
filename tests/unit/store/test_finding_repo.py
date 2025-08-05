from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import pytest

from dripleg.diagnosis.batch import diagnose_survey
from dripleg.errors import NotFoundError
from dripleg.loss.cost import CostBasis
from dripleg.loss.emissions import FACTORS
from dripleg.loss.energy import EnergyModel
from dripleg.loss.register import LossRegister, build_loss_register
from dripleg.model.plant import Site
from dripleg.model.register import TrapRegister
from dripleg.model.tags import TrapTag
from dripleg.repair.recommend import Action, Recommendation
from dripleg.repair.workorder import WorkOrder
from dripleg.store.db import Database
from dripleg.store.finding_repo import FindingRepository, WorkOrderRepository
from dripleg.store.migrations import migrate
from dripleg.store.plant_repo import PlantRepository
from dripleg.store.survey_repo import SurveyRepository
from dripleg.survey.condition import TrapCondition
from dripleg.survey.observation import Observation
from dripleg.survey.survey import Survey
from dripleg.units.money import Money
from tests.support.build import DAY, a_station, pipe, probe

BLOWING = {"ultrasonic": probe(70.0, 0), "temperature": pipe(345.0, 258.0)}
HEALTHY = {"ultrasonic": probe(32.0, 2), "temperature": pipe(350.0, 200.0)}


@pytest.fixture
def book() -> Iterator[Database]:
    db = Database()
    migrate(db)
    PlantRepository(db).save_site(Site.of("WRX1", "Wrexham paper mill", "Bryn"))
    yield db
    db.close()


def stored(
    book: Database, rows: list[tuple[str, dict[str, object]]], reference: str = "S2025-1"
) -> LossRegister:
    register = TrapRegister([a_station(tag=TrapTag.parse(tag)) for tag, _ in rows])
    survey = Survey("WRX1", reference, "Spring", "Vane", DAY - dt.timedelta(days=1))
    for tag, readings in rows:
        survey.record(
            Observation(
                tag=TrapTag.parse(tag),
                observed_on=DAY,
                technician="R Ellis",
                reported_condition=TrapCondition.OK,
                **readings,  # type: ignore[arg-type]
            )
        )
    SurveyRepository(book).save(survey)
    return build_loss_register(
        register,
        diagnose_survey(register, survey),
        EnergyModel.typical(),
        CostBasis.typical(),
        FACTORS["natural_gas"],
    )


def test_a_register_goes_in_and_comes_back(book: Database) -> None:
    repo = FindingRepository(book)
    register = stored(book, [("B12-MP-1", BLOWING), ("B12-MP-2", HEALTHY)])
    assert repo.save_register("WRX1", register) == 2
    findings = repo.for_survey("WRX1", "s2025-1")
    assert [str(f.tag) for f in findings] == ["B12-MP-0001", "B12-MP-0002"]


def test_a_finding_keeps_its_numbers_and_its_rules(book: Database) -> None:
    repo = FindingRepository(book)
    repo.save_register("WRX1", stored(book, [("B12-MP-1", BLOWING)]))
    finding = repo.for_survey("WRX1", "S2025-1")[0]
    assert finding.diagnosed is TrapCondition.BLOWING_THROUGH
    assert finding.reported is TrapCondition.OK
    assert not finding.agreed_with_technician
    assert finding.confidence > 0.5
    assert finding.pounds_per_hour > 0
    assert finding.is_losing
    assert "COR-1" in finding.rules_fired
    assert any("differs" in flag for flag in finding.flags)


def test_a_healthy_finding_carries_zeroes(book: Database) -> None:
    repo = FindingRepository(book)
    repo.save_register("WRX1", stored(book, [("B12-MP-2", HEALTHY)]))
    finding = repo.for_survey("WRX1", "S2025-1")[0]
    assert not finding.is_losing
    assert finding.annual_cost == Money.zero()
    assert finding.agreed_with_technician


def test_saving_a_register_twice_replaces_it(book: Database) -> None:
    repo = FindingRepository(book)
    register = stored(book, [("B12-MP-1", BLOWING)])
    repo.save_register("WRX1", register)
    repo.save_register("WRX1", register)
    assert len(repo.for_survey("WRX1", "S2025-1")) == 1


def test_the_total_adds_the_findings_up(book: Database) -> None:
    repo = FindingRepository(book)
    register = stored(book, [("B12-MP-1", BLOWING), ("B12-MP-2", HEALTHY)])
    repo.save_register("WRX1", register)
    assert repo.total_cost("WRX1", "S2025-1") == register.total_cost
    assert repo.total_cost("WRX1", "NOPE") == Money.zero()


def test_the_dearest_findings_come_back_first(book: Database) -> None:
    repo = FindingRepository(book)
    repo.save_register("WRX1", stored(book, [("B12-MP-1", BLOWING), ("B12-MP-2", HEALTHY)]))
    dearest = repo.dearest("WRX1")
    assert len(dearest) == 1
    assert str(dearest[0].tag) == "B12-MP-0001"


def test_the_history_of_one_trap_across_surveys(book: Database) -> None:
    repo = FindingRepository(book)
    repo.save_register("WRX1", stored(book, [("B12-MP-1", BLOWING)], "S2025-1"))
    second = Survey("WRX1", "S2025-2", "Autumn", "Vane", dt.date(2025, 10, 1))
    second.record(
        Observation(
            tag=TrapTag.parse("B12-MP-1"),
            observed_on=dt.date(2025, 10, 2),
            technician="J Pike",
            reported_condition=TrapCondition.OK,
            **HEALTHY,  # type: ignore[arg-type]
        )
    )
    SurveyRepository(book).save(second)
    register = TrapRegister([a_station(tag=TrapTag.parse("B12-MP-1"))])
    repo.save_register(
        "WRX1",
        build_loss_register(
            register,
            diagnose_survey(register, second),
            EnergyModel.typical(),
            CostBasis.typical(),
            FACTORS["natural_gas"],
        ),
    )
    history = repo.history_for("WRX1", "B12-MP-1")
    assert [f.survey_reference for f in history] == ["S2025-1", "S2025-2"]
    assert history[-1].diagnosed is TrapCondition.OK


def test_printing_a_stored_finding(book: Database) -> None:
    repo = FindingRepository(book)
    repo.save_register("WRX1", stored(book, [("B12-MP-1", BLOWING)]))
    assert str(repo.for_survey("WRX1", "S2025-1")[0]).startswith("B12-MP-0001 blowing through $")


def a_job() -> Recommendation:
    return Recommendation(
        tag=TrapTag.parse("B12-MP-0043"),
        action=Action.REPAIR,
        reason="blowing through",
        parts=Money.from_dollars("64.40"),
        labour=Money.from_dollars("74.00"),
        permit=Money.zero(),
        annual_saving=Money.from_dollars("2613.18"),
    )


def test_a_work_order_round_trips(book: Database) -> None:
    repo = WorkOrderRepository(book)
    order = WorkOrder.raise_for("WO-00001", a_job(), on=DAY, within_days=30)
    order.issue("A Frayne", DAY)
    order.start(DAY + dt.timedelta(days=2))
    order.complete(DAY + dt.timedelta(days=2), Money.from_dollars("151.20"))
    repo.save("WRX1", order)
    stored_order = repo.get("wo-00001")
    assert stored_order.assigned_to == "A Frayne"
    assert stored_order.actual_cost == Money.from_dollars("151.20")
    assert stored_order.completed_on == DAY + dt.timedelta(days=2)
    assert len(stored_order.history) == 3


def test_a_verified_order_round_trips(book: Database) -> None:
    repo = WorkOrderRepository(book)
    order = WorkOrder.raise_for("WO-00001", a_job(), on=DAY, within_days=30)
    order.issue("A Frayne", DAY)
    order.start(DAY)
    order.complete(DAY + dt.timedelta(days=1))
    order.verify(DAY + dt.timedelta(days=20))
    repo.save("WRX1", order)
    assert repo.get("WO-00001").verified_on == DAY + dt.timedelta(days=20)
    assert repo.open_orders("WRX1") == []


def test_a_missing_order(book: Database) -> None:
    with pytest.raises(NotFoundError, match="work order"):
        WorkOrderRepository(book).get("WO-99999")


def test_open_overdue_and_awaiting_verification(book: Database) -> None:
    repo = WorkOrderRepository(book)
    first = WorkOrder.raise_for("WO-00001", a_job(), on=DAY, within_days=5)
    second = WorkOrder.raise_for("WO-00002", a_job(), on=DAY, within_days=90)
    second.issue("A Frayne", DAY)
    second.start(DAY)
    second.complete(DAY + dt.timedelta(days=1))
    repo.save("WRX1", first)
    repo.save("WRX1", second)
    assert [o.number for o in repo.open_orders("WRX1")] == ["WO-00001", "WO-00002"]
    late = DAY + dt.timedelta(days=30)
    assert [o.number for o in repo.overdue_on("WRX1", late)] == ["WO-00001"]
    assert [o.number for o in repo.awaiting_verification("WRX1")] == ["WO-00002"]


def test_every_order_on_one_trap(book: Database) -> None:
    repo = WorkOrderRepository(book)
    repo.save("WRX1", WorkOrder.raise_for("WO-00001", a_job(), on=DAY, within_days=30))
    repo.save(
        "WRX1",
        WorkOrder.raise_for("WO-00002", a_job(), on=DAY + dt.timedelta(days=200), within_days=30),
    )
    assert [o.number for o in repo.for_tag("WRX1", "B12-MP-43")] == ["WO-00001", "WO-00002"]
    assert repo.for_tag("WRX1", "B12-MP-99") == []


def test_the_next_number_counts_what_is_there(book: Database) -> None:
    repo = WorkOrderRepository(book)
    assert repo.next_number("WRX1") == "WO-00001"
    repo.save("WRX1", WorkOrder.raise_for("WO-00001", a_job(), on=DAY, within_days=30))
    assert repo.next_number("WRX1") == "WO-00002"
    assert repo.next_number("WRX1", "job") == "JOB-00002"


def test_saving_an_order_twice_updates_it(book: Database) -> None:
    repo = WorkOrderRepository(book)
    order = WorkOrder.raise_for("WO-00001", a_job(), on=DAY, within_days=30)
    repo.save("WRX1", order)
    order.issue("A Frayne", DAY)
    repo.save("WRX1", order)
    stored_order = repo.get("WO-00001")
    assert stored_order.assigned_to == "A Frayne"
    assert len(stored_order.history) == 1
