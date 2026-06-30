"""`dripleg survey`: opening one, importing readings into it, closing it."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import click

from dripleg.cli.context import Context
from dripleg.cli.loading import diagnosis_for, register_for
from dripleg.cli.output import emit_facts, emit_lines, emit_rows
from dripleg.errors import ConflictError
from dripleg.ingest.profile import profile_named
from dripleg.ingest.reader import read_survey_csv, write_quarantine
from dripleg.programme.calibration import calibrate
from dripleg.report.survey_report import build_survey_report
from dripleg.report.table import Column
from dripleg.store.survey_repo import SurveyRepository
from dripleg.survey.survey import Survey

__all__ = ["survey_group"]


@click.group("survey")
def survey_group() -> None:
    """Surveys: one pass over the plant."""


@survey_group.command("open")
@click.argument("reference")
@click.argument("name")
@click.option("--contractor", required=True, help="Who walked it.")
@click.option("--started", required=True, help="First day on site.")
@click.pass_obj
def survey_open(context: Context, reference: str, name: str, contractor: str, started: str) -> None:
    """Open a survey to import readings into."""

    repo = SurveyRepository(context.book)
    if repo.find(context.site(), reference) is not None:
        raise ConflictError(f"survey {reference} is already open on this book")
    survey = Survey(
        site=context.site(),
        reference=reference,
        name=name,
        contractor=contractor,
        started_on=dt.date.fromisoformat(started),
    )
    repo.save(survey)
    emit_facts(
        context,
        {
            "reference": survey.reference,
            "name": survey.name,
            "contractor": survey.contractor,
            "started_on": survey.started_on.isoformat(),
            "readings": 0,
        },
    )


@survey_group.command("import")
@click.argument("reference")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--profile", "profile_name", default=None, help="Force a mapping profile.")
@click.option("--dry-run", is_flag=True, help="Read the file and report, write nothing.")
@click.option(
    "--quarantine",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write the rows that would not read to this file.",
)
@click.pass_obj
def survey_import(
    context: Context,
    reference: str,
    path: Path,
    profile_name: str | None,
    dry_run: bool,
    quarantine: Path | None,
) -> None:
    """Read a tablet export into an open survey."""

    profile = None if profile_name is None else profile_named(profile_name)
    result = read_survey_csv(path.read_text(encoding="utf-8"), profile)
    repo = SurveyRepository(context.book)
    survey = repo.get(context.site(), reference)
    written = 0
    for observation in result.observations:
        if survey.find(observation.tag) is not None:
            survey.amend(observation)
        else:
            survey.record(observation)
        written += 1
    if not dry_run:
        repo.save(survey)
    if quarantine is not None and result.quarantined:
        write_quarantine(result.quarantined, quarantine)
    emit_facts(
        context,
        {
            "file": str(path),
            "profile": result.profile.name,
            "content_hash": result.content_hash,
            "read": result.read,
            "quarantined": result.rejected,
            "written": 0 if dry_run else written,
            "dry_run": dry_run,
            "quarantine_file": "" if quarantine is None else str(quarantine),
            "quarantine": [str(row) for row in result.quarantined],
        },
    )


@survey_group.command("close")
@click.argument("reference")
@click.option("--on", required=True, help="Last day on site.")
@click.pass_obj
def survey_close(context: Context, reference: str, on: str) -> None:
    """Close a survey so nothing else lands in it."""

    repo = SurveyRepository(context.book)
    survey = repo.get(context.site(), reference)
    survey.close(dt.date.fromisoformat(on))
    repo.save(survey)
    emit_facts(
        context,
        {
            "reference": survey.reference,
            "finished_on": on,
            "readings": len(survey),
        },
    )


@survey_group.command("list")
@click.pass_obj
def survey_list(context: Context) -> None:
    """Every survey on the book."""

    repo = SurveyRepository(context.book)
    surveys = [repo.get(context.site(), ref) for ref in repo.list_references(context.site())]
    emit_rows(
        context,
        [
            Column("reference"),
            Column("name"),
            Column("contractor"),
            Column("started"),
            Column("finished"),
            Column.number("readings"),
        ],
        [
            (
                s.reference,
                s.name,
                s.contractor,
                s.started_on.isoformat(),
                "open" if s.finished_on is None else s.finished_on.isoformat(),
                len(s),
            )
            for s in surveys
        ],
        keys=["reference", "name", "contractor", "started", "finished", "readings"],
        empty="no surveys yet",
    )


@survey_group.command("calibration")
@click.argument("reference")
@click.option("--rated-only", is_flag=True, help="Only technicians with enough readings.")
@click.pass_obj
def survey_calibration(context: Context, reference: str, rated_only: bool) -> None:
    """How each technician's own codes line up with the rules."""

    survey = SurveyRepository(context.book).get(context.site(), reference)
    report = calibrate(survey, diagnosis_for(context, reference))
    records = report.reportable() if rated_only else report.records
    emit_rows(
        context,
        [
            Column("technician"),
            Column.number("read"),
            Column.number("agreed"),
            Column.number("over"),
            Column.number("under"),
            Column.number("agreement"),
            Column.number("two method"),
            Column("leans"),
        ],
        [
            (
                record.technician,
                record.read,
                record.agreed,
                record.over_called,
                record.under_called,
                f"{record.agreement_rate:.0%}" if record.is_reportable else "n/a",
                f"{record.two_method_rate:.0%}",
                record.leans,
            )
            for record in records
        ],
        keys=[
            "technician",
            "read",
            "agreed",
            "over_called",
            "under_called",
            "agreement",
            "two_method",
            "leans",
        ],
        empty="nobody has read anything on that survey",
    )


@survey_group.command("readings")
@click.argument("tag")
@click.pass_obj
def survey_readings(context: Context, tag: str) -> None:
    """Every reading ever taken on one trap, oldest first."""

    readings = SurveyRepository(context.book).readings_for(context.site(), tag)
    emit_rows(
        context,
        [
            Column("date"),
            Column("by"),
            Column("code"),
            Column.number("dB"),
            Column.number("cycles/min"),
            Column.number("in"),
            Column.number("out"),
            Column("note", max_width=30),
        ],
        [
            (
                observation.observed_on.isoformat(),
                observation.technician,
                observation.reported_condition.label,
                (
                    f"{observation.ultrasonic.decibels:.0f}"
                    if observation.ultrasonic is not None
                    else ""
                ),
                (
                    f"{observation.cycles_per_minute:.1f}"
                    if observation.cycles_per_minute is not None
                    else ""
                ),
                (
                    f"{observation.temperature.upstream.fahrenheit:.0f}"
                    if observation.temperature is not None
                    else ""
                ),
                (
                    f"{observation.temperature.downstream.fahrenheit:.0f}"
                    if observation.temperature is not None
                    else ""
                ),
                observation.note,
            )
            for observation in readings
        ],
        keys=[
            "date",
            "by",
            "code",
            "decibels",
            "cycles_per_minute",
            "upstream",
            "downstream",
            "note",
        ],
        empty="nothing has ever been read on that trap",
    )


@survey_group.command("report")
@click.argument("reference")
@click.pass_obj
def survey_report(context: Context, reference: str) -> None:
    """The survey report: coverage first, then what was found."""

    register = register_for(context)
    survey = SurveyRepository(context.book).get(context.site(), reference)
    report = build_survey_report(register, survey, diagnosis_for(context, reference))
    emit_lines(context, report.lines(), report.as_dict())
