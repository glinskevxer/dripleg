from __future__ import annotations

import pytest

from dripleg.model.attributes import ServiceType
from dripleg.model.register import TrapRegister
from dripleg.model.tags import TrapTag
from dripleg.sizing.audit import audit_sizing
from dripleg.sizing.capacity import SizingVerdict
from dripleg.units.temperature import Temperature
from tests.support.build import a_model, a_station


def a_register(rows: list[dict[str, object]]) -> TrapRegister:
    return TrapRegister([a_station(**row) for row in rows])


def sized(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "tag": TrapTag.parse("B12-MP-1"),
        "service": ServiceType.DRIP,
        "pipe_nominal": "4",
        "run_length_ft": 180.0,
    }
    row.update(overrides)
    return row


def test_a_station_with_geometry_is_sized() -> None:
    audit = audit_sizing(a_register([sized()]))
    assert audit.checked == 1
    assert audit.skipped == 0
    assert audit.coverage == pytest.approx(1.0)


def test_a_station_without_geometry_is_named_not_dropped() -> None:
    audit = audit_sizing(a_register([sized(), {"tag": TrapTag.parse("B12-MP-2")}]))
    assert audit.checked == 1
    assert [str(t) for t in audit.no_geometry] == ["B12-MP-0002"]
    assert audit.coverage == pytest.approx(0.5)


def test_a_service_nobody_can_size_is_named_separately() -> None:
    audit = audit_sizing(
        a_register(
            [sized(), sized(tag=TrapTag.parse("B12-MP-2"), service=ServiceType.PROCESS_COIL)]
        )
    )
    assert [str(t) for t in audit.not_sizeable] == ["B12-MP-0002"]
    assert audit.no_geometry == []


def test_a_separator_is_sizeable_and_a_tracer_is_not() -> None:
    audit = audit_sizing(
        a_register(
            [
                sized(service=ServiceType.SEPARATOR),
                sized(tag=TrapTag.parse("B12-MP-2"), service=ServiceType.TRACER),
            ]
        )
    )
    assert audit.checked == 1
    assert len(audit.not_sizeable) == 1


def test_the_warm_up_load_is_the_one_checked_against() -> None:
    row = audit_sizing(a_register([sized()])).rows[0]
    assert row.warmup_pph > row.running_pph
    assert row.check.load.pounds_per_hour == pytest.approx(row.warmup_pph)


def test_a_bare_line_makes_more_running_load() -> None:
    lagged = audit_sizing(a_register([sized()])).rows[0]
    bare = audit_sizing(a_register([sized(insulated=False)])).rows[0]
    assert bare.running_pph > lagged.running_pph
    assert bare.warmup_pph == pytest.approx(lagged.warmup_pph)


def test_a_long_run_on_a_small_trap_reads_undersized() -> None:
    audit = audit_sizing(a_register([sized(pipe_nominal="12", run_length_ft=600.0)]))
    assert audit.rows[0].verdict is SizingVerdict.UNDERSIZED
    assert len(audit.wrong) == 1


def test_a_short_run_on_a_big_trap_reads_oversized() -> None:
    audit = audit_sizing(
        a_register([sized(pipe_nominal="1/2", run_length_ft=10.0, model=a_model(orifice=0.25))])
    )
    assert audit.rows[0].verdict is SizingVerdict.OVERSIZED


def test_a_slower_warm_up_makes_a_smaller_load() -> None:
    quick = audit_sizing(a_register([sized(warmup_minutes=15.0)])).rows[0]
    slow = audit_sizing(a_register([sized(warmup_minutes=120.0)])).rows[0]
    assert quick.warmup_pph > slow.warmup_pph


def test_a_colder_start_makes_a_bigger_load() -> None:
    register = a_register([sized()])
    warm = audit_sizing(register, cold=Temperature.from_fahrenheit(100.0)).rows[0]
    freezing = audit_sizing(register, cold=Temperature.from_fahrenheit(20.0)).rows[0]
    assert freezing.warmup_pph > warm.warmup_pph


def test_the_counts_cover_every_verdict() -> None:
    counts = audit_sizing(a_register([sized()])).counts()
    assert set(counts) == {"undersized", "correct", "oversized"}
    assert sum(counts.values()) == 1


def test_the_wrong_list_leads_with_the_tightest() -> None:
    audit = audit_sizing(
        a_register(
            [
                sized(pipe_nominal="12", run_length_ft=600.0),
                sized(tag=TrapTag.parse("B12-MP-2"), pipe_nominal="8", run_length_ft=400.0),
            ]
        )
    )
    ratios = [row.check.ratio for row in audit.wrong]
    assert ratios == sorted(ratios)


def test_an_empty_register_has_no_coverage() -> None:
    audit = audit_sizing(TrapRegister())
    assert audit.checked == 0
    assert audit.coverage == 0.0
    assert audit.wrong == []


def test_printing_a_row_and_an_audit() -> None:
    audit = audit_sizing(a_register([sized()]))
    assert str(audit.rows[0]).startswith("B12-MP-0001 ")
    assert str(audit).endswith("undersized, 0 oversized") or "oversized" in str(audit)
