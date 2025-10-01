from __future__ import annotations

import json
from pathlib import Path

import pytest

from dripleg.tools.coverage_gate import FileCoverage, Report, main, read_report


def a_payload(total: float, files: dict[str, tuple[int, int, float]]) -> dict[str, object]:
    return {
        "totals": {"percent_covered": total},
        "files": {
            name: {
                "summary": {
                    "num_statements": statements,
                    "missing_lines": missing,
                    "percent_covered": percent,
                }
            }
            for name, (statements, missing, percent) in files.items()
        },
    }


def write(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_a_report_reads_its_files(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        a_payload(93.5, {"src/dripleg/units/money.py": (100, 5, 95.0)}),
    )
    report = read_report(path)
    assert report.percent == pytest.approx(93.5)
    assert len(report.files) == 1
    assert report.files[0].covered == 95


def test_a_file_knows_whether_it_is_under_a_floor() -> None:
    entry = FileCoverage("a.py", 100, 40, 60.0)
    assert entry.is_under(70.0)
    assert not entry.is_under(50.0)
    assert str(entry) == "a.py   60.0%  40 of 100 missed"


def test_the_worst_file_comes_back() -> None:
    report = Report(
        percent=90.0,
        files=[FileCoverage("a.py", 10, 0, 100.0), FileCoverage("b.py", 10, 6, 40.0)],
    )
    worst = report.worst
    assert worst is not None
    assert worst.path == "b.py"
    assert Report(percent=0.0, files=[]).worst is None


def test_files_under_the_floor_come_back_worst_first() -> None:
    report = Report(
        percent=90.0,
        files=[
            FileCoverage("a.py", 10, 3, 70.0),
            FileCoverage("b.py", 10, 6, 40.0),
            FileCoverage("c.py", 10, 0, 100.0),
        ],
    )
    assert [f.path for f in report.under(80.0)] == ["b.py", "a.py"]


def test_a_clean_run_has_no_problems() -> None:
    report = Report(percent=95.0, files=[FileCoverage("a.py", 10, 0, 100.0)])
    assert report.problems(90.0, 70.0) == []


def test_the_overall_floor_is_reported_first() -> None:
    report = Report(percent=85.0, files=[FileCoverage("a.py", 10, 6, 40.0)])
    problems = report.problems(90.0, 70.0)
    assert problems[0].startswith("coverage is 85.0%")
    assert "a.py" in problems[1]


def test_one_bad_file_fails_even_at_a_good_overall(tmp_path: Path) -> None:
    report = Report(
        percent=95.0,
        files=[FileCoverage("a.py", 900, 0, 100.0), FileCoverage("b.py", 100, 60, 40.0)],
    )
    problems = report.problems(90.0, 70.0)
    assert len(problems) == 1
    assert "b.py" in problems[0]


def test_the_gate_passes_a_good_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path, a_payload(95.0, {"a.py": (10, 0, 100.0)}))
    assert main(["--report", str(path), "--floor", "90"]) == 0
    assert "coverage 95.0%" in capsys.readouterr().out


def test_the_gate_fails_a_bad_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path, a_payload(85.0, {"a.py": (10, 6, 40.0)}))
    assert main(["--report", str(path), "--floor", "90"]) == 1
    err = capsys.readouterr().err
    assert "under the 90.0% floor" in err
    assert "a.py" in err


def test_a_missing_report_is_a_different_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--report", str(tmp_path / "nope.json")]) == 2
    assert "no coverage report" in capsys.readouterr().err


def test_the_file_floor_can_be_moved(tmp_path: Path) -> None:
    path = write(tmp_path, a_payload(95.0, {"a.py": (10, 6, 40.0)}))
    assert main(["--report", str(path), "--floor", "90", "--file-floor", "30"]) == 0
    assert main(["--report", str(path), "--floor", "90", "--file-floor", "50"]) == 1
