from __future__ import annotations

import dripleg.report as reports
from dripleg.report.base import Rendered


def test_every_report_type_is_on_the_package() -> None:
    for name in (
        "SurveyReport",
        "LossReport",
        "WorkReport",
        "ProgrammeReport",
        "TrendReport",
        "EnergyReport",
        "Scorecard",
    ):
        assert hasattr(reports, name)
        assert name in reports.__all__


def test_every_builder_is_on_the_package() -> None:
    for name in (
        "build_survey_report",
        "build_loss_report",
        "build_work_report",
        "build_programme_report",
        "build_trend_report",
        "build_energy_report",
        "build_scorecard",
    ):
        assert callable(getattr(reports, name))
        assert name in reports.__all__


def test_every_exported_report_renders_the_same_way() -> None:
    for name in reports.__all__:
        thing = getattr(reports, name)
        if name in {"Report", "Rendered"}:
            continue
        if isinstance(thing, type) and name.endswith(("Report", "Scorecard")):
            assert issubclass(thing, Rendered)


def test_the_table_pieces_come_through_too() -> None:
    assert reports.Column("tag").heading == "tag"
    assert reports.Align.RIGHT.is_right
    table = reports.Table([reports.Column("a")])
    table.add(["1"])
    assert len(table) == 1


def test_the_package_exports_are_sorted_and_complete() -> None:
    assert list(reports.__all__) == sorted(reports.__all__)
    for name in reports.__all__:
        assert hasattr(reports, name)
