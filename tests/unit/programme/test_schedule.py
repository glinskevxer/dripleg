from __future__ import annotations

import datetime as dt

import pytest

from dripleg.errors import ValidationError
from dripleg.model.attributes import ServiceType
from dripleg.model.register import TrapRegister
from dripleg.model.tags import TrapTag
from dripleg.programme.schedule import AFTER_FAILURE_MONTHS, build_schedule
from dripleg.survey.condition import TrapCondition
from tests.support.build import a_station

TODAY = dt.date(2025, 9, 1)
LAST_YEAR = dt.date(2024, 9, 1)


def a_register(tags: list[tuple[str, ServiceType]]) -> TrapRegister:
    return TrapRegister(
        [a_station(tag=TrapTag.parse(tag), service=service) for tag, service in tags]
    )


def history(
    entries: list[tuple[str, dt.date, TrapCondition]],
) -> dict[TrapTag, tuple[dt.date, TrapCondition]]:
    return {TrapTag.parse(tag): (day, condition) for tag, day, condition in entries}


def test_a_trap_never_surveyed_has_no_due_date() -> None:
    schedule = build_schedule(a_register([("B12-MP-1", ServiceType.DRIP)]), {}, on=TODAY)
    entry = schedule.find("B12-MP-1")
    assert entry is not None
    assert entry.never_surveyed
    assert entry.due_on is None
    assert entry.is_due_by(TODAY)
    assert not entry.is_overdue_on(TODAY)
    assert entry.days_late_on(TODAY) == 0


def test_a_passing_trap_comes_round_on_its_service_interval() -> None:
    schedule = build_schedule(
        a_register([("B12-MP-1", ServiceType.DRIP)]),
        history([("B12-MP-1", LAST_YEAR, TrapCondition.OK)]),
        on=TODAY,
    )
    entry = schedule.find("B12-MP-1")
    assert entry is not None
    assert entry.due_on == dt.date(2025, 9, 1)
    assert entry.interval_months == 12


def test_a_turbine_drain_comes_round_twice_as_often() -> None:
    schedule = build_schedule(
        a_register([("B12-MP-1", ServiceType.TURBINE_DRAIN)]),
        history([("B12-MP-1", LAST_YEAR, TrapCondition.OK)]),
        on=TODAY,
    )
    entry = schedule.find("B12-MP-1")
    assert entry is not None
    assert entry.due_on == dt.date(2025, 3, 1)
    assert entry.interval_months == 6


def test_a_failed_trap_comes_round_inside_a_quarter() -> None:
    schedule = build_schedule(
        a_register([("B12-MP-1", ServiceType.TRACER)]),
        history([("B12-MP-1", LAST_YEAR, TrapCondition.BLOWING_THROUGH)]),
        on=TODAY,
    )
    entry = schedule.find("B12-MP-1")
    assert entry is not None
    assert entry.interval_months == AFTER_FAILURE_MONTHS
    assert entry.due_on == dt.date(2024, 12, 1)
    assert entry.shortened_after_failure


def test_the_failure_rule_never_lengthens_an_interval() -> None:
    schedule = build_schedule(
        a_register([("B12-MP-1", ServiceType.DRIP)]),
        history([("B12-MP-1", LAST_YEAR, TrapCondition.FAILED_CLOSED)]),
        on=TODAY,
    )
    entry = schedule.find("B12-MP-1")
    assert entry is not None
    assert entry.interval_months == 3


def test_an_unfound_trap_is_not_a_failure_for_scheduling() -> None:
    schedule = build_schedule(
        a_register([("B12-MP-1", ServiceType.DRIP)]),
        history([("B12-MP-1", LAST_YEAR, TrapCondition.NOT_FOUND)]),
        on=TODAY,
    )
    entry = schedule.find("B12-MP-1")
    assert entry is not None
    assert entry.interval_months == 12
    assert not entry.shortened_after_failure


def test_a_station_override_still_wins_for_a_passing_trap() -> None:
    register = TrapRegister([a_station(tag=TrapTag.parse("B12-MP-1"), interval_months_override=1)])
    schedule = build_schedule(
        register, history([("B12-MP-1", LAST_YEAR, TrapCondition.OK)]), on=TODAY
    )
    entry = schedule.find("B12-MP-1")
    assert entry is not None
    assert entry.interval_months == 1


def test_a_trap_pulled_before_today_is_not_scheduled() -> None:
    register = TrapRegister(
        [a_station(tag=TrapTag.parse("B12-MP-1"), removed_on=dt.date(2025, 1, 1))]
    )
    assert len(build_schedule(register, {}, on=TODAY)) == 0


def test_overdue_is_sorted_by_how_late() -> None:
    schedule = build_schedule(
        a_register([("B12-MP-1", ServiceType.DRIP), ("B12-MP-2", ServiceType.TURBINE_DRAIN)]),
        history(
            [
                ("B12-MP-1", dt.date(2024, 6, 1), TrapCondition.OK),
                ("B12-MP-2", dt.date(2024, 6, 1), TrapCondition.OK),
            ]
        ),
        on=TODAY,
    )
    late = schedule.overdue_on(TODAY)
    assert [str(e.tag) for e in late] == ["B12-MP-0002", "B12-MP-0001"]
    assert late[0].days_late_on(TODAY) > late[1].days_late_on(TODAY)


def test_never_surveyed_is_counted_separately_from_overdue() -> None:
    schedule = build_schedule(
        a_register([("B12-MP-1", ServiceType.DRIP), ("B12-MP-2", ServiceType.DRIP)]),
        history([("B12-MP-1", dt.date(2023, 1, 1), TrapCondition.OK)]),
        on=TODAY,
    )
    assert [str(e.tag) for e in schedule.never_surveyed()] == ["B12-MP-0002"]
    assert [str(e.tag) for e in schedule.overdue_on(TODAY)] == ["B12-MP-0001"]


def test_everything_is_due_by_a_far_enough_day() -> None:
    schedule = build_schedule(
        a_register([("B12-MP-1", ServiceType.DRIP), ("B12-MP-2", ServiceType.DRIP)]),
        history([("B12-MP-1", LAST_YEAR, TrapCondition.OK)]),
        on=TODAY,
    )
    assert len(schedule.due_by(dt.date(2030, 1, 1))) == 2


def test_the_shortened_list_is_the_repeat_offenders() -> None:
    schedule = build_schedule(
        a_register([("B12-MP-1", ServiceType.DRIP), ("B12-MP-2", ServiceType.DRIP)]),
        history(
            [
                ("B12-MP-1", LAST_YEAR, TrapCondition.LEAKING),
                ("B12-MP-2", LAST_YEAR, TrapCondition.OK),
            ]
        ),
        on=TODAY,
    )
    assert [str(e.tag) for e in schedule.shortened()] == ["B12-MP-0001"]


def test_a_window_takes_what_falls_inside_it() -> None:
    schedule = build_schedule(
        a_register([("B12-MP-1", ServiceType.DRIP), ("B12-MP-2", ServiceType.DRIP)]),
        history(
            [
                ("B12-MP-1", dt.date(2025, 1, 15), TrapCondition.OK),
                ("B12-MP-2", dt.date(2025, 6, 15), TrapCondition.OK),
            ]
        ),
        on=TODAY,
    )
    window = schedule.in_window(dt.date(2026, 1, 1), dt.date(2026, 3, 1))
    assert [str(e.tag) for e in window] == ["B12-MP-0001"]
    with pytest.raises(ValidationError, match="ends after it starts"):
        schedule.in_window(dt.date(2026, 3, 1), dt.date(2026, 1, 1))


def test_compliance_counts_late_and_unlooked_at_together() -> None:
    schedule = build_schedule(
        a_register([(f"B12-MP-{n}", ServiceType.DRIP) for n in (1, 2, 3, 4)]),
        history(
            [
                ("B12-MP-1", dt.date(2025, 6, 1), TrapCondition.OK),
                ("B12-MP-2", dt.date(2025, 6, 1), TrapCondition.OK),
                ("B12-MP-3", dt.date(2023, 1, 1), TrapCondition.OK),
            ]
        ),
        on=TODAY,
    )
    assert schedule.compliance_on(TODAY) == pytest.approx(0.5)


def test_an_empty_programme_is_fully_compliant() -> None:
    schedule = build_schedule(TrapRegister(), {}, on=TODAY)
    assert schedule.compliance_on(TODAY) == 1.0
    assert str(schedule) == "0 stations, 0 never surveyed"


def test_the_monthly_workload() -> None:
    schedule = build_schedule(
        a_register([("B12-MP-1", ServiceType.DRIP), ("B12-MP-2", ServiceType.DRIP)]),
        history(
            [
                ("B12-MP-1", dt.date(2025, 3, 10), TrapCondition.OK),
                ("B12-MP-2", dt.date(2025, 3, 20), TrapCondition.OK),
            ]
        ),
        on=TODAY,
    )
    workload = schedule.workload_by_month(2026)
    assert workload[3] == 2
    assert sum(workload.values()) == 2
    assert len(workload) == 12


def test_printing_an_entry_and_a_schedule() -> None:
    schedule = build_schedule(
        a_register([("B12-MP-1", ServiceType.DRIP), ("B12-MP-2", ServiceType.DRIP)]),
        history([("B12-MP-1", LAST_YEAR, TrapCondition.OK)]),
        on=TODAY,
    )
    entries = {str(e.tag): str(e) for e in schedule.entries}
    assert entries["B12-MP-0001"] == "B12-MP-0001 due 2025-09-01 (12 month interval)"
    assert entries["B12-MP-0002"] == "B12-MP-0002 never surveyed"
    assert str(schedule) == "2 stations, 1 never surveyed"
