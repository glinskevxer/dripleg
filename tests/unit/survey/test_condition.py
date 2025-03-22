from __future__ import annotations

import pytest

from dripleg.errors import ValidationError
from dripleg.survey.condition import TrapCondition


def test_only_the_two_unfound_codes_were_not_assessed() -> None:
    unassessed = {c for c in TrapCondition if not c.was_assessed}
    assert unassessed == {TrapCondition.NOT_FOUND, TrapCondition.INACCESSIBLE}


def test_an_isolated_trap_was_assessed_but_is_not_in_service() -> None:
    assert TrapCondition.OUT_OF_SERVICE.was_assessed
    assert not TrapCondition.OUT_OF_SERVICE.is_in_service
    assert TrapCondition.OK.is_in_service
    assert not TrapCondition.NOT_FOUND.is_in_service


def test_the_codes_that_waste_steam() -> None:
    wasteful = {c for c in TrapCondition if c.wastes_steam}
    assert wasteful == {
        TrapCondition.LEAKING,
        TrapCondition.BLOWING_THROUGH,
        TrapCondition.RAPID_CYCLING,
    }


def test_the_codes_that_back_condensate_up() -> None:
    blocking = {c for c in TrapCondition if c.blocks_condensate}
    assert blocking == {TrapCondition.FAILED_CLOSED, TrapCondition.PLUGGED}


def test_wasting_and_blocking_are_different_questions() -> None:
    assert TrapCondition.BLOWING_THROUGH.wastes_steam
    assert not TrapCondition.BLOWING_THROUGH.blocks_condensate
    assert TrapCondition.FAILED_CLOSED.blocks_condensate
    assert not TrapCondition.FAILED_CLOSED.wastes_steam
    assert TrapCondition.FAILED_CLOSED.is_failure


def test_a_pass_is_not_a_failure_and_needs_no_repair() -> None:
    assert not TrapCondition.OK.is_failure
    assert not TrapCondition.OK.needs_repair
    assert not TrapCondition.NO_LOAD.is_failure


def test_a_trap_that_could_not_be_found_still_goes_on_the_list() -> None:
    assert not TrapCondition.NOT_FOUND.is_failure
    assert TrapCondition.NOT_FOUND.needs_repair
    assert TrapCondition.INACCESSIBLE.needs_repair


def test_a_blowing_trap_passes_the_whole_orifice() -> None:
    assert TrapCondition.BLOWING_THROUGH.severity_factor == 1.0
    assert TrapCondition.LEAKING.severity_factor == 0.25
    assert TrapCondition.RAPID_CYCLING.severity_factor == 0.10


def test_nothing_that_is_not_wasting_has_a_severity() -> None:
    for condition in TrapCondition:
        if not condition.wastes_steam:
            assert condition.severity_factor == 0.0


def test_report_order_puts_the_worst_first_and_the_unfound_last() -> None:
    order = TrapCondition.in_report_order()
    assert order[0] is TrapCondition.BLOWING_THROUGH
    assert order[-1] is TrapCondition.INACCESSIBLE
    assert len(order) == len(TrapCondition)
    assert len({c.rank for c in TrapCondition}) == len(TrapCondition)


def test_the_failure_list_is_ranked() -> None:
    failures = TrapCondition.failures()
    assert failures[0] is TrapCondition.BLOWING_THROUGH
    assert TrapCondition.OK not in failures
    assert TrapCondition.NOT_FOUND not in failures
    assert len(failures) == 5


def test_parsing_the_plain_codes() -> None:
    assert TrapCondition.parse("blowing_through") is TrapCondition.BLOWING_THROUGH
    assert TrapCondition.parse(" Blowing Through ") is TrapCondition.BLOWING_THROUGH
    assert TrapCondition.parse("failed-closed") is TrapCondition.FAILED_CLOSED


def test_parsing_what_the_three_tablets_actually_write() -> None:
    assert TrapCondition.parse("PASS") is TrapCondition.OK
    assert TrapCondition.parse("failed open") is TrapCondition.BLOWING_THROUGH
    assert TrapCondition.parse("cold") is TrapCondition.FAILED_CLOSED
    assert TrapCondition.parse("strainer") is TrapCondition.PLUGGED
    assert TrapCondition.parse("waterlogged") is TrapCondition.FLOODED
    assert TrapCondition.parse("valved off") is TrapCondition.OUT_OF_SERVICE
    assert TrapCondition.parse("missing") is TrapCondition.NOT_FOUND
    assert TrapCondition.parse("no access") is TrapCondition.INACCESSIBLE


def test_parsing_something_nobody_writes() -> None:
    with pytest.raises(ValidationError, match="not a trap condition"):
        TrapCondition.parse("looked fine to me")


def test_labels_read_like_english() -> None:
    assert TrapCondition.BLOWING_THROUGH.label == "blowing through"
    assert TrapCondition.OK.label == "ok"
