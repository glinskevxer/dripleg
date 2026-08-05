"""Printing: plain text for people, json for whatever reads it next.

Every report in here answers `lines()` and `as_dict()`, and the two carry the
same numbers. Importing them from the package rather than from the module they
happen to live in means a report can be moved without breaking a caller, which
has already had to happen twice.
"""

from __future__ import annotations

from dripleg.report.base import Rendered, Report
from dripleg.report.energy_report import EnergyReport, build_energy_report
from dripleg.report.loss_report import LossReport, build_loss_report
from dripleg.report.programme_report import ProgrammeReport, build_programme_report
from dripleg.report.scorecard import Scorecard, ScoreLine, build_scorecard
from dripleg.report.survey_report import SurveyReport, build_survey_report
from dripleg.report.table import Align, Column, Table
from dripleg.report.trend_report import TrendReport, build_trend_report
from dripleg.report.work_report import JobLine, WorkReport, build_work_report

__all__ = [
    "Align",
    "Column",
    "EnergyReport",
    "JobLine",
    "LossReport",
    "ProgrammeReport",
    "Rendered",
    "Report",
    "ScoreLine",
    "Scorecard",
    "SurveyReport",
    "Table",
    "TrendReport",
    "WorkReport",
    "build_energy_report",
    "build_loss_report",
    "build_programme_report",
    "build_scorecard",
    "build_survey_report",
    "build_trend_report",
    "build_work_report",
]
