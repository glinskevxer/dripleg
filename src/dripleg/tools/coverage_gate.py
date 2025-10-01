"""Fail the build when coverage slips, and say which files did it.

`--fail-under` on coverage itself gives a single number and no idea where the
hole is, which turns a red build into ten minutes of opening the html report.
This reads the json coverage writes and names the files under the floor, worst
first, so the failure message is the fix list.

There is a second floor on top of the overall one: no single file may fall too
far, because a package can sit at ninety two percent overall with one module at
forty and the overall number hides it.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

__all__ = ["FileCoverage", "Report", "main", "read_report"]

DEFAULT_FLOOR = 90.0
DEFAULT_FILE_FLOOR = 70.0


@dataclass(frozen=True)
class FileCoverage:
    """One file's line and branch coverage."""

    path: str
    statements: int
    missing: int
    percent: float

    @property
    def covered(self) -> int:
        return self.statements - self.missing

    def is_under(self, floor: float) -> bool:
        return self.percent < floor

    def __str__(self) -> str:
        return f"{self.path}  {self.percent:5.1f}%  {self.missing} of {self.statements} missed"


@dataclass(frozen=True)
class Report:
    """A whole coverage run."""

    percent: float
    files: list[FileCoverage]

    def under(self, floor: float) -> list[FileCoverage]:
        return sorted(
            (f for f in self.files if f.is_under(floor)), key=lambda f: (f.percent, f.path)
        )

    @property
    def worst(self) -> FileCoverage | None:
        if not self.files:
            return None
        return min(self.files, key=lambda f: (f.percent, f.path))

    def problems(self, floor: float, file_floor: float) -> list[str]:
        """Everything wrong with this run, in the order to fix it."""

        found: list[str] = []
        if self.percent < floor:
            found.append(f"coverage is {self.percent:.1f}%, under the {floor:.1f}% floor")
        for entry in self.under(file_floor):
            found.append(f"  {entry}")
        return found


def read_report(path: Path) -> Report:
    """Read the json `coverage json` writes."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    files = [
        FileCoverage(
            path=name,
            statements=int(data["summary"]["num_statements"]),
            missing=int(data["summary"]["missing_lines"]),
            percent=float(data["summary"]["percent_covered"]),
        )
        for name, data in sorted(payload.get("files", {}).items())
    ]
    return Report(percent=float(payload["totals"]["percent_covered"]), files=files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hold the build to a coverage floor.")
    parser.add_argument("--report", default="coverage.json", type=Path)
    parser.add_argument("--floor", default=DEFAULT_FLOOR, type=float)
    parser.add_argument("--file-floor", default=DEFAULT_FILE_FLOOR, type=float)
    args = parser.parse_args(argv)
    if not args.report.exists():
        print(f"no coverage report at {args.report}", file=sys.stderr)
        return 2
    report = read_report(args.report)
    problems = report.problems(args.floor, args.file_floor)
    if not problems:
        print(f"coverage {report.percent:.1f}%, floor {args.floor:.1f}%")
        return 0
    for line in problems:
        print(line, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
