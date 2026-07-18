"""Everything that has to be true before a version goes out.

None of it is clever and all of it has been got wrong at least once somewhere:

- every dependency is pinned to an exact version, runtime and development
  alike. A range is a build that passes today and fails on a Tuesday.
- the version in `pyproject.toml` and the version in the package agree. They
  are two files and they drift.
- the changelog has a heading for the version being released, so a release
  without a note is a red build rather than a silent one.
- the console entry point names something importable, because that only fails
  once the wheel is installed and by then it has been published.

It reads `pyproject.toml` as text rather than parsing it. The file is small,
the checks are on lines, and a tomllib parse would need the file to be valid
before it could tell you it is not.
"""

from __future__ import annotations

import argparse
import importlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from dripleg import __version__

__all__ = ["DEFAULT_CHANGELOG", "DEFAULT_PYPROJECT", "Pin", "check", "main", "pins"]

DEFAULT_PYPROJECT = Path("pyproject.toml")
DEFAULT_CHANGELOG = Path("CHANGELOG.md")

_PIN = re.compile(r'"(?P<name>[A-Za-z0-9_.\-]+)(?P<spec>[^"]*)"')
_VERSION = re.compile(r'^version\s*=\s*"(?P<version>[^"]+)"', re.MULTILINE)
_SCRIPT = re.compile(
    r'^(?P<name>[\w-]+)\s*=\s*"(?P<target>[\w.]+):(?P<function>\w+)"', re.MULTILINE
)


@dataclass(frozen=True)
class Pin:
    """One dependency line and whether it is pinned."""

    name: str
    spec: str

    @property
    def is_exact(self) -> bool:
        return self.spec.startswith("==")

    def __str__(self) -> str:
        return f"{self.name}{self.spec}"


def _sections(text: str) -> list[str]:
    """The dependency arrays, as raw text."""

    found: list[str] = []
    for marker in ("dependencies = [", "dev = [", "requires = ["):
        start = 0
        while True:
            at = text.find(marker, start)
            if at < 0:
                break
            end = text.index("]", at)
            found.append(text[at + len(marker) : end])
            start = end
    return found


def pins(text: str) -> list[Pin]:
    """Every dependency this project declares."""

    found: list[Pin] = []
    for section in _sections(text):
        for match in _PIN.finditer(section):
            found.append(Pin(name=match.group("name"), spec=match.group("spec")))
    return found


def check(pyproject: str, changelog: str, version: str) -> list[str]:
    """Everything wrong with this release."""

    problems: list[str] = []
    for pin in pins(pyproject):
        if not pin.is_exact:
            problems.append(f"{pin.name} is not pinned exactly: {pin}")
    declared = _VERSION.search(pyproject)
    if declared is None:
        problems.append("pyproject.toml has no version in it")
    elif declared.group("version") != version:
        problems.append(
            f"pyproject.toml says {declared.group('version')} and the package says {version}"
        )
    if f"## {version}" not in changelog:
        problems.append(f"the changelog has no heading for {version}")
    for script in _SCRIPT.finditer(pyproject):
        target = script.group("target")
        try:
            module = importlib.import_module(target)
        except ImportError:
            problems.append(f"the {script.group('name')} script names {target}, which is not there")
            continue
        if not hasattr(module, script.group("function")):
            problems.append(
                f"the {script.group('name')} script names {target}:{script.group('function')}, "
                "which is not there"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check this build is fit to release.")
    parser.add_argument("--pyproject", default=DEFAULT_PYPROJECT, type=Path)
    parser.add_argument("--changelog", default=DEFAULT_CHANGELOG, type=Path)
    args = parser.parse_args(argv)
    for path in (args.pyproject, args.changelog):
        if not path.exists():
            print(f"there is no {path}", file=sys.stderr)
            return 2
    problems = check(
        args.pyproject.read_text(encoding="utf-8"),
        args.changelog.read_text(encoding="utf-8"),
        __version__,
    )
    if problems:
        for line in problems:
            print(line, file=sys.stderr)
        return 1
    print(f"version {__version__}, {len(pins(args.pyproject.read_text()))} pins, all exact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
