from __future__ import annotations

from pathlib import Path

import pytest

from dripleg.cli.context import Context
from dripleg.cli.loading import (
    basis_for,
    diagnosis_for,
    loss_register_for,
    register_for,
    survey_for,
    work_list_for,
)
from dripleg.errors import NotFoundError
from tests.support.cli import make_book, run

EXPORT = (
    "tag,date,by,condition,db,seconds,cycles,up_f,down_f,amb_f,glass,psig,note\n"
    "B12-MP-1,2025-04-08,R Ellis,pass,70,30,0,345,258,74,,,\n"
    "B12-MP-2,2025-04-08,R Ellis,pass,32,30,2,350,200,,,,\n"
)


@pytest.fixture
def context(tmp_path: Path) -> Context:
    target = make_book(tmp_path, name="wrx1.sqlite3")
    for tag in ("B12-MP-1", "B12-MP-2"):
        run(
            target,
            "--site",
            "WRX1",
            "trap",
            "add",
            tag,
            "--model",
            "Halden/TD52",
            "--installed",
            "2021-06-14",
        )
    run(
        target,
        "--site",
        "WRX1",
        "survey",
        "open",
        "S2025-1",
        "Spring",
        "--contractor",
        "Vane Energy",
        "--started",
        "2025-04-07",
    )
    export = Path(target).parent / "export.csv"
    export.write_text(EXPORT, encoding="utf-8")
    run(target, "--site", "WRX1", "survey", "import", "S2025-1", str(export))
    return Context(book_path=target, site_code="WRX1")


def test_the_register_loads_with_its_headers(context: Context) -> None:
    register = register_for(context)
    assert len(register) == 2
    assert register.get("B12-MP-1").header.operating_pressure.psig == pytest.approx(125.0)
    context.close()


def test_the_survey_loads_with_its_readings(context: Context) -> None:
    survey = survey_for(context, "S2025-1")
    assert len(survey) == 2
    assert survey.contractor == "Vane Energy"
    context.close()


def test_a_missing_survey_is_reported(context: Context) -> None:
    with pytest.raises(NotFoundError, match="survey"):
        survey_for(context, "S2099-9")
    context.close()


def test_the_basis_falls_back_to_the_worked_example(context: Context) -> None:
    basis = basis_for(context)
    assert basis.costs.fuel.unit == "MMBtu"
    assert basis.factor.name == "natural gas"
    context.close()


def test_the_diagnosis_judges_every_reading(context: Context) -> None:
    diagnosis = diagnosis_for(context, "S2025-1")
    assert len(diagnosis) == 2
    assert len(diagnosis.failures()) == 1
    context.close()


def test_the_loss_register_costs_every_row(context: Context) -> None:
    losses = loss_register_for(context, "S2025-1")
    assert len(losses) == 2
    assert len(losses.losing) == 1
    assert losses.total_cost.cents > 0
    context.close()


def test_the_work_list_ranks_the_jobs(context: Context) -> None:
    work = work_list_for(context, "S2025-1")
    assert len(work.actionable) == 1
    assert work.total_saving.cents > 0
    context.close()


def test_the_loads_agree_with_each_other(context: Context) -> None:
    losses = loss_register_for(context, "S2025-1")
    work = work_list_for(context, "S2025-1")
    assert work.total_saving == losses.total_cost
    context.close()
