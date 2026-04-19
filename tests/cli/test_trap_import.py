from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.cli import make_book, run

REGISTER = (
    "tag,manufacturer,model,installed,service,access,criticality,profile,"
    "destination,strainer,valves,interval,note\n"
    "B12-MP-1,Halden,TD52,2021-06-14,drip,ground_level,nuisance,CONT,,y,2,,by the door\n"
    "B12-MP-2,Halden,TD52,2022-01-04,tracer,ladder,comfort,CONT,atmosphere,n,1,3,\n"
)


@pytest.fixture
def book(tmp_path: Path) -> str:
    return make_book(tmp_path, name="wrx1.sqlite3")


@pytest.fixture
def register(tmp_path: Path) -> Path:
    path = tmp_path / "register.csv"
    path.write_text(REGISTER, encoding="utf-8")
    return path


def test_a_register_imports(book: str, register: Path) -> None:
    result = run(book, "--site", "WRX1", "--json", "trap", "import", str(register))
    payload = json.loads(result.output)
    assert payload["read"] == 2
    assert payload["written"] == 2
    assert payload["quarantined"] == 0
    listed = json.loads(run(book, "--site", "WRX1", "--json", "trap", "list").output)
    assert len(listed) == 2


def test_a_dry_run_writes_nothing(book: str, register: Path) -> None:
    payload = json.loads(
        run(book, "--site", "WRX1", "--json", "trap", "import", str(register), "--dry-run").output
    )
    assert payload["written"] == 0
    assert json.loads(run(book, "--site", "WRX1", "--json", "trap", "list").output) == []


def test_a_bad_row_is_quarantined_and_the_rest_goes_in(book: str, tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text(REGISTER.replace("B12-MP-2", "C3-MP-9"), encoding="utf-8")
    payload = json.loads(run(book, "--site", "WRX1", "--json", "trap", "import", str(path)).output)
    assert payload["read"] == 1
    assert payload["quarantined"] == 1
    assert payload["quarantine"][0].startswith("line 3:")


def test_importing_twice_updates_rather_than_duplicating(book: str, register: Path) -> None:
    run(book, "--site", "WRX1", "trap", "import", str(register))
    run(book, "--site", "WRX1", "trap", "import", str(register))
    listed = json.loads(run(book, "--site", "WRX1", "--json", "trap", "list").output)
    assert len(listed) == 2


def test_a_file_missing_a_column_is_refused(book: str, tmp_path: Path) -> None:
    path = tmp_path / "short.csv"
    path.write_text("tag,manufacturer,model\nB12-MP-1,Halden,TD52\n", encoding="utf-8")
    assert run(book, "--site", "WRX1", "trap", "import", str(path)).exit_code != 0


def test_the_export_round_trips_through_the_import(book: str, register: Path) -> None:
    run(book, "--site", "WRX1", "trap", "import", str(register))
    exported = run(book, "--site", "WRX1", "trap", "export")
    assert exported.exit_code == 0
    again = Path(str(register)).with_name("again.csv")
    again.write_text(exported.output, encoding="utf-8")
    payload = json.loads(run(book, "--site", "WRX1", "--json", "trap", "import", str(again)).output)
    assert payload["read"] == 2
    assert payload["quarantined"] == 0


def test_the_export_header_matches_what_the_import_wants(book: str, register: Path) -> None:
    run(book, "--site", "WRX1", "trap", "import", str(register))
    header = run(book, "--site", "WRX1", "trap", "export").output.splitlines()[0]
    assert header.startswith("tag,manufacturer,model,installed")
    assert header.endswith("note")


def test_the_export_carries_the_optional_columns(book: str, register: Path) -> None:
    run(book, "--site", "WRX1", "trap", "import", str(register))
    rows = run(book, "--site", "WRX1", "trap", "export").output.splitlines()[1:]
    tracer = next(row for row in rows if row.startswith("B12-MP-0002"))
    assert ",atmosphere," in tracer
    assert ",n,1,3," in tracer


def test_the_export_can_be_cut_to_the_live_traps(book: str, register: Path) -> None:
    run(book, "--site", "WRX1", "trap", "import", str(register))
    run(book, "--site", "WRX1", "trap", "retire", "B12-MP-1", "--on", "2024-03-01")
    live = run(book, "--site", "WRX1", "trap", "export", "--live").output.splitlines()
    everything = run(book, "--site", "WRX1", "trap", "export").output.splitlines()
    assert len(live) == 2
    assert len(everything) == 3


def test_an_empty_register_exports_just_the_header(book: str) -> None:
    lines = run(book, "--site", "WRX1", "trap", "export").output.splitlines()
    assert len(lines) == 1
