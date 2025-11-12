from __future__ import annotations

import pytest

from dripleg.errors import ValidationError
from dripleg.model.tags import TrapTag
from dripleg.programme.trend import Trend, compare_surveys
from dripleg.store.finding_repo import StoredFinding
from dripleg.survey.condition import TrapCondition
from dripleg.units.money import Money

BLOW = TrapCondition.BLOWING_THROUGH
OK = TrapCondition.OK
COLD = TrapCondition.FAILED_CLOSED


def finding(
    tag: str, condition: TrapCondition, reference: str = "S1", cost: str = "0.00"
) -> StoredFinding:
    return StoredFinding(
        tag=TrapTag.parse(tag),
        survey_reference=reference,
        diagnosed=condition,
        reported=condition,
        confidence=0.8,
        flags=(),
        rules_fired=(),
        pounds_per_hour=48.0 if condition.wastes_steam else 0.0,
        pounds_per_year=420000.0 if condition.wastes_steam else 0.0,
        fuel_mmbtu_per_year=500.0 if condition.wastes_steam else 0.0,
        tonnes_co2e=26.0 if condition.wastes_steam else 0.0,
        annual_cost=Money.from_dollars(cost),
    )


def a_trend() -> Trend:
    earlier = [
        finding("B12-MP-1", BLOW, "S1", "2600.00"),
        finding("B12-MP-2", BLOW, "S1", "2600.00"),
        finding("B12-MP-3", OK, "S1"),
        finding("B12-MP-4", OK, "S1"),
        finding("B12-MP-5", OK, "S1"),
    ]
    later = [
        finding("B12-MP-1", OK, "S2"),
        finding("B12-MP-2", BLOW, "S2", "2700.00"),
        finding("B12-MP-3", COLD, "S2"),
        finding("B12-MP-4", OK, "S2"),
        finding("B12-MP-6", OK, "S2"),
    ]
    return compare_surveys(earlier, later)


def test_only_the_traps_in_both_surveys_are_compared() -> None:
    trend = a_trend()
    assert trend.compared == 4
    assert [str(t) for t in trend.only_earlier] == ["B12-MP-0005"]
    assert [str(t) for t in trend.only_later] == ["B12-MP-0006"]


def test_the_four_buckets_are_kept_apart() -> None:
    counts = a_trend().counts()
    assert counts == {
        "fixed": 1,
        "still failing": 1,
        "newly failed": 1,
        "unchanged": 1,
    }


def test_each_bucket_names_the_right_traps() -> None:
    trend = a_trend()
    assert [str(m.tag) for m in trend.in_bucket("fixed")] == ["B12-MP-0001"]
    assert [str(m.tag) for m in trend.in_bucket("still failing")] == ["B12-MP-0002"]
    assert [str(m.tag) for m in trend.in_bucket("newly failed")] == ["B12-MP-0003"]
    assert [str(m.tag) for m in trend.in_bucket("unchanged")] == ["B12-MP-0004"]


def test_a_bucket_nobody_named_is_refused() -> None:
    with pytest.raises(ValidationError, match="is not a bucket"):
        a_trend().in_bucket("mostly fine")


def test_the_failure_rates_move() -> None:
    trend = a_trend()
    assert trend.failing_before == 2
    assert trend.failing_after == 2
    assert trend.failure_rate_before == pytest.approx(0.5)
    assert trend.failure_rate_after == pytest.approx(0.5)
    assert not trend.is_improving


def test_a_programme_that_is_working_says_so() -> None:
    earlier = [finding("B12-MP-1", BLOW, "S1", "2600.00"), finding("B12-MP-2", BLOW, "S1")]
    later = [finding("B12-MP-1", OK, "S2"), finding("B12-MP-2", OK, "S2")]
    trend = compare_surveys(earlier, later)
    assert trend.is_improving
    assert trend.counts()["fixed"] == 2


def test_the_money_moves_with_the_conditions() -> None:
    trend = a_trend()
    assert trend.cost_before == Money.from_dollars("5200.00")
    assert trend.cost_after == Money.from_dollars("2700.00")
    assert trend.saving == Money.from_dollars("2500.00")


def test_the_unfixed_cost_is_the_traps_that_failed_twice() -> None:
    assert a_trend().unfixed_cost == Money.from_dollars("2700.00")


def test_a_movement_knows_its_own_saving() -> None:
    trend = a_trend()
    fixed = trend.in_bucket("fixed")[0]
    assert fixed.saving == Money.from_dollars("2600.00")
    assert fixed.was_failing
    assert not fixed.is_failing


def test_comparing_two_surveys_that_share_nothing() -> None:
    trend = compare_surveys([finding("B12-MP-1", BLOW, "S1")], [finding("C3-MP-1", OK, "S2")])
    assert trend.compared == 0
    assert trend.failure_rate_before == 0.0
    assert trend.cost_before.is_zero
    assert not trend.is_improving


def test_comparing_nothing_at_all_is_refused() -> None:
    with pytest.raises(ValidationError, match="nothing to compare"):
        compare_surveys([], [])


def test_a_survey_against_an_empty_one() -> None:
    trend = compare_surveys([finding("B12-MP-1", BLOW, "S1")], [])
    assert trend.earlier == "S1"
    assert trend.later == ""
    assert trend.compared == 0
    assert [str(t) for t in trend.only_earlier] == ["B12-MP-0001"]


def test_printing_a_movement_and_a_trend() -> None:
    trend = a_trend()
    assert str(trend.in_bucket("fixed")[0]) == ("B12-MP-0001 blowing through to ok (fixed)")
    assert str(trend) == "S1 to S2: 1 fixed, 1 still failing, 1 newly failed"
