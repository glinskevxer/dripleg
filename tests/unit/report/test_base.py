from __future__ import annotations

import io
from dataclasses import dataclass

from dripleg.report.base import Rendered, Report
from dripleg.report.loss_report import LossReport
from dripleg.report.programme_report import ProgrammeReport
from dripleg.report.survey_report import SurveyReport
from dripleg.report.trend_report import TrendReport
from dripleg.report.work_report import WorkReport


@dataclass(frozen=True)
class Tiny(Rendered):
    first: str
    second: str

    def lines(self) -> list[str]:
        return [self.first, self.second]

    def as_dict(self) -> dict[str, object]:
        return {"first": self.first, "second": self.second}


def test_rendering_joins_the_lines() -> None:
    report = Tiny("one", "two")
    assert report.render() == "one\ntwo"
    assert str(report) == report.render()


def test_writing_out_says_how_many_lines_went() -> None:
    stream = io.StringIO()
    assert Tiny("one", "two").write_to(stream) == 2
    assert stream.getvalue() == "one\ntwo\n"


def test_the_mixin_on_its_own_has_no_lines() -> None:
    class Bare(Rendered):
        pass

    try:
        Bare().render()
    except NotImplementedError:
        return
    raise AssertionError("a report with no lines should not render")


def test_every_report_in_the_build_is_one() -> None:
    for kind in (SurveyReport, LossReport, WorkReport, ProgrammeReport, TrendReport):
        assert issubclass(kind, Rendered)
        assert hasattr(kind, "lines")
        assert hasattr(kind, "as_dict")


def test_the_protocol_recognises_a_report() -> None:
    assert isinstance(Tiny("one", "two"), Report)


def test_the_protocol_refuses_something_that_is_not_one() -> None:
    class NotAReport:
        pass

    assert not isinstance(NotAReport(), Report)
