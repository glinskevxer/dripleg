from __future__ import annotations

import inspect
from pathlib import Path

from dripleg import thresholds


def test_every_threshold_carries_a_reason() -> None:
    source = inspect.getsource(thresholds)
    for name in thresholds.__all__:
        assert f"{name} = " in source
        after = source.split(f"{name} = ", 1)[1]
        assert '"""' in after.split("\n\n", 1)[0] or after.lstrip().startswith("CRITICAL")


def test_the_thresholds_are_in_the_ranges_they_have_to_be() -> None:
    assert 0.0 < thresholds.CRITICAL_BACK_PRESSURE_RATIO < 1.0
    assert 0.0 < thresholds.OUTLET_MARGIN_F < 50.0
    assert thresholds.COLD_INLET_F > thresholds.AMBIENT_MARGIN_F
    assert thresholds.SUBCOOLED_FLOOR_F == 0.0
    assert 0.0 < thresholds.PRESSURE_DISAGREEMENT < 1.0


def test_nothing_writes_the_critical_ratio_out_by_hand() -> None:
    offenders = []
    for path in sorted(Path("src/dripleg").rglob("*.py")):
        if path.name == "thresholds.py":
            continue
        if "0.577" in path.read_text(encoding="utf-8"):
            offenders.append(str(path))
    assert offenders == []


def test_the_loss_layer_uses_the_same_ratio() -> None:
    from dripleg.loss.napier import CRITICAL_PRESSURE_RATIO

    assert CRITICAL_PRESSURE_RATIO == thresholds.CRITICAL_BACK_PRESSURE_RATIO


def test_the_header_and_the_context_agree_about_choking() -> None:
    from dripleg.diagnosis.context import DiagnosisContext
    from tests.support.build import a_header, a_reading, a_station

    station = a_station(header=a_header(operating=30.0, discharge=25.0))
    context = DiagnosisContext(station, a_reading())
    assert context.is_choked == station.header.discharge_is_choked
