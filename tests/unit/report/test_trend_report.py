from __future__ import annotations

import pytest

from dripleg.model.tags import TrapTag
from dripleg.programme.trend import compare_surveys
from dripleg.report.trend_report import TrendReport, build_trend_report
from dripleg.store.finding_repo import StoredFinding
from dripleg.survey.condition import TrapCondition
from dripleg.units.money import Money

BLOW = TrapCondition.BLOWING_THROUGH
OK = TrapCondition.OK


def finding(tag: str, condition: TrapCondition, reference: str, cost: str = "0.00"):  # type: ignore[no-untyped-def]
    return StoredFinding(
        tag=TrapTag.parse(tag),
        survey_reference=reference,
        diagnosed=condition,
        reported=condition,
        confidence=0.8,
        flags=(),
        rules_fired=(),
        pounds_per_hour=48.0 if condition.wastes_steam else 0.0,
        pounds_per_year=0.0,
        fuel_mmbtu_per_year=0.0,
        tonnes_co2e=0.0,
        annual_cost=Money.from_dollars(cost),
    )


def a_report() -> TrendReport:
    earlier = [
        finding("B12-MP-1", BLOW, "S1", "2600.00"),
        finding("B12-MP-2", BLOW, "S1", "2600.00"),
        finding("B12-MP-3", OK, "S1"),
        finding("B12-MP-5", OK, "S1"),
    ]
    later = [
        finding("B12-MP-1", OK, "S2"),
        finding("B12-MP-2", BLOW, "S2", "2700.00"),
        finding("B12-MP-3", BLOW, "S2", "1400.00"),
        finding("B12-MP-6", OK, "S2"),
    ]
    return build_trend_report(compare_surveys(earlier, later))


def test_a_flat_rate_reads_as_flat_rather_than_up() -> None:
    report = a_report()
    assert report.direction == "flat"
    assert "failure rate flat at 66.7% over 3 traps" in report.headline
    assert not report.is_improving


def test_a_rising_rate_reads_as_up() -> None:
    earlier = [finding("B12-MP-1", OK, "S1"), finding("B12-MP-2", OK, "S1")]
    later = [finding("B12-MP-1", BLOW, "S2", "2600.00"), finding("B12-MP-2", OK, "S2")]
    report = build_trend_report(compare_surveys(earlier, later))
    assert report.direction == "up"
    assert "up from 0.0% to 50.0%" in report.headline


def test_a_falling_rate_reads_as_down() -> None:
    earlier = [finding("B12-MP-1", BLOW, "S1", "2600.00")]
    later = [finding("B12-MP-1", OK, "S2")]
    report = build_trend_report(compare_surveys(earlier, later))
    assert "down from" in report.headline
    assert report.is_improving


def test_the_summary_carries_the_four_buckets() -> None:
    lines = "\n".join(a_report().summary_lines())
    assert "fixed           1" in lines
    assert "still failing   1" in lines
    assert "newly failed    1" in lines


def test_the_money_lines_add_up() -> None:
    report = a_report()
    assert report.cost_before == Money.from_dollars("5200.00")
    assert report.cost_after == Money.from_dollars("4100.00")
    assert report.saving == Money.from_dollars("1100.00")


def test_the_unfixed_traps_are_named_dearest_first() -> None:
    report = a_report()
    assert [row[0] for row in report.unfixed_rows] == ["B12-MP-0002"]
    assert report.unfixed_cost == Money.from_dollars("2700.00")
    assert "failed at both surveys" in report.render()


def test_a_clean_comparison_leaves_the_unfixed_block_out() -> None:
    earlier = [finding("B12-MP-1", BLOW, "S1", "2600.00")]
    later = [finding("B12-MP-1", OK, "S2")]
    report = build_trend_report(compare_surveys(earlier, later))
    assert report.unfixed_rows == []
    assert "failed at both surveys" not in report.render()


def test_the_traps_read_on_only_one_survey_are_listed() -> None:
    report = a_report()
    assert report.only_earlier == ["B12-MP-0005"]
    assert report.only_later == ["B12-MP-0006"]
    rendered = report.render()
    assert "read this time and not last: B12-MP-0006" in rendered
    assert "read last time and not this: B12-MP-0005" in rendered


def test_the_json_shape_carries_the_buckets_and_the_money() -> None:
    payload = a_report().as_dict()
    assert payload["earlier"] == "S1"
    assert payload["later"] == "S2"
    assert payload["compared"] == 3
    assert payload["counts"] == {
        "fixed": 1,
        "still failing": 1,
        "newly failed": 1,
        "unchanged": 0,
    }
    assert payload["saving_cents"] == 110000
    unfixed = payload["unfixed"]
    assert isinstance(unfixed, list)
    assert len(unfixed) == 1


def test_the_rates_are_rounded_in_json() -> None:
    payload = a_report().as_dict()
    assert payload["failure_rate_before"] == pytest.approx(0.6667, abs=0.0001)
    assert payload["failure_rate_after"] == pytest.approx(0.6667, abs=0.0001)
    assert payload["direction"] == "flat"


def test_the_table_holds_one_line_per_unfixed_trap() -> None:
    table = a_report().unfixed_table()
    assert len(table) == 1
    assert "B12-MP-0002" in table.render()
