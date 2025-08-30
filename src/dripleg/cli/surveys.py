"""`dripleg survey`: opening one, importing readings into it, closing it."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import click

from dripleg.cli.context import Context
from dripleg.cli.output import emit_facts, emit_lines, emit_rows
from dripleg.diagnosis.batch import diagnose_survey
from dripleg.errors import ConflictError
from dripleg.ingest.profile import profile_named
from dripleg.ingest.reader import read_survey_csv
from dripleg.report.survey_report import build_survey_report
from dripleg.report.table import Column
from dripleg.store.station_repo import StationRepository
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
@click.pass_obj
def survey_import(
    context: Context,
    reference: str,
    path: Path,
    profile_name: str | None,
    dry_run: bool,
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


@survey_group.command("report")
@click.argument("reference")
@click.pass_obj
def survey_report(context: Context, reference: str) -> None:
    """The survey report: coverage first, then what was found."""

    register = StationRepository(context.book).load_register(context.site())
    survey = SurveyRepository(context.book).get(context.site(), reference)
    diagnosis = diagnose_survey(register, survey)
    report = build_survey_report(register, survey, diagnosis)
    emit_lines(context, report.lines(), report.as_dict())
