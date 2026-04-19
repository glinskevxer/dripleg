"""Standing a small plant up through the command line, for the CLI tests.

Fourteen CLI test modules had the same forty line fixture in them: init, a
site, an area, a header, a model, a profile and a handful of traps. They had
drifted, of course, so a change to `trap add` broke eleven of them in eleven
slightly different ways.

Everything here goes through the CLI rather than through the repositories on
purpose. A fixture that writes straight to the store can set up states the
commands cannot produce, and a test that only passes from such a state is
testing something no user can reach.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner, Result

from dripleg.cli.main import cli

__all__ = [
    "SURVEY_HEADER",
    "add_traps",
    "import_survey",
    "make_book",
    "run",
    "survey_file",
]

SURVEY_HEADER = "tag,date,by,condition,db,seconds,cycles,up_f,down_f,amb_f,glass,psig,note"


def run(book: str, *args: str) -> Result:
    """Invoke the command line against one book."""

    return CliRunner().invoke(cli, ["--book", book, *args])


def make_book(
    tmp_path: Path,
    *,
    name: str = "wrx1.sqlite3",
    areas: tuple[str, ...] = ("B12",),
    psig: float = 125.0,
    discharge_psig: float = 15.0,
) -> str:
    """A book with a site, one header per area, a model and a profile."""

    target = str(tmp_path / name)
    run(target, "init")
    run(target, "site", "add", "WRX1", "Wrexham paper mill", "--operator", "Bryn Paper")
    for area in areas:
        run(target, "area", "add", area, f"Area {area}", "--cost-centre", "PM2")
        run(
            target,
            "header",
            "add",
            area,
            "MP",
            f"{area} main",
            "--psig",
            str(psig),
            "--discharge-psig",
            str(discharge_psig),
        )
    run(
        target,
        "model",
        "add",
        "Halden",
        "TD52",
        "--principle",
        "thermodynamic_disc",
        "--orifice",
        "0.093",
        "--pmo",
        "600",
        "--price",
        "184.00",
    )
    run(target, "profile", "add", "CONT", "Continuous")
    return target


def add_traps(book: str, tags: list[str], *extra: str) -> None:
    """Put a handful of stations on the register."""

    for tag in tags:
        run(
            book,
            "trap",
            "add",
            tag,
            "--model",
            "Halden/TD52",
            "--installed",
            "2021-06-14",
            *extra,
        )


def survey_file(tmp_path: Path, name: str, rows: list[str]) -> Path:
    """Write a fieldbook export out for `survey import` to read."""

    path = tmp_path / name
    path.write_text("\n".join([SURVEY_HEADER, *rows]) + "\n", encoding="utf-8")
    return path


def import_survey(
    book: str,
    tmp_path: Path,
    reference: str,
    started: str,
    rows: list[str],
    *,
    name: str = "Season",
    contractor: str = "Vane Energy",
) -> Result:
    """Open a survey and import a set of readings into it."""

    run(
        book,
        "survey",
        "open",
        reference,
        name,
        "--contractor",
        contractor,
        "--started",
        started,
    )
    path = survey_file(tmp_path, f"{reference}.csv", rows)
    return run(book, "survey", "import", reference, str(path))
