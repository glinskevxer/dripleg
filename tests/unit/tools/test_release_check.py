from __future__ import annotations

from pathlib import Path

import pytest

from dripleg import __version__
from dripleg.tools.release_check import (
    DEFAULT_CHANGELOG,
    DEFAULT_PYPROJECT,
    Pin,
    check,
    main,
    pins,
)

GOOD = """
[project]
name = "dripleg"
version = "9.9.9"
dependencies = ["click==8.1.8"]

[project.optional-dependencies]
dev = ["pytest==8.3.5", "ruff==0.9.7"]

[project.scripts]
dripleg = "dripleg.cli.main:run"
"""


def test_this_build_is_fit_to_release() -> None:
    problems = check(
        DEFAULT_PYPROJECT.read_text(encoding="utf-8"),
        DEFAULT_CHANGELOG.read_text(encoding="utf-8"),
        __version__,
    )
    assert problems == []


def test_every_pin_in_this_build_is_exact() -> None:
    declared = pins(DEFAULT_PYPROJECT.read_text(encoding="utf-8"))
    assert declared
    assert all(pin.is_exact for pin in declared)


def test_a_pin_knows_whether_it_is_exact() -> None:
    assert Pin("click", "==8.1.8").is_exact
    assert not Pin("click", ">=8.1").is_exact
    assert not Pin("click", "").is_exact
    assert str(Pin("click", "==8.1.8")) == "click==8.1.8"


def test_a_loose_pin_is_caught() -> None:
    problems = check(GOOD.replace("click==8.1.8", "click>=8.1"), "## 9.9.9\n", "9.9.9")
    assert problems == ["click is not pinned exactly: click>=8.1"]


def test_a_loose_dev_pin_is_caught_too() -> None:
    problems = check(GOOD.replace("ruff==0.9.7", "ruff"), "## 9.9.9\n", "9.9.9")
    assert any("ruff" in line for line in problems)


def test_a_version_mismatch_is_caught() -> None:
    problems = check(GOOD, "## 1.2.3\n", "1.2.3")
    assert any("says 9.9.9 and the package says 1.2.3" in line for line in problems)


def test_a_missing_version_is_caught() -> None:
    problems = check(GOOD.replace('version = "9.9.9"', ""), "## 9.9.9\n", "9.9.9")
    assert any("no version in it" in line for line in problems)


def test_a_changelog_with_no_entry_is_caught() -> None:
    problems = check(GOOD, "# Changelog\n\n## 1.0.0\n", "9.9.9")
    assert any("no heading for 9.9.9" in line for line in problems)


def test_a_script_naming_nothing_is_caught() -> None:
    problems = check(
        GOOD.replace("dripleg.cli.main:run", "dripleg.cli.nowhere:run"), "## 9.9.9\n", "9.9.9"
    )
    assert any("which is not there" in line for line in problems)


def test_a_script_naming_a_missing_function_is_caught() -> None:
    problems = check(
        GOOD.replace("dripleg.cli.main:run", "dripleg.cli.main:nowhere"), "## 9.9.9\n", "9.9.9"
    )
    assert any("nowhere" in line for line in problems)


def test_the_gate_passes_on_this_build(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    out = capsys.readouterr().out
    assert __version__ in out
    assert "all exact" in out


def test_a_missing_file_is_a_different_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--pyproject", str(tmp_path / "nope.toml")]) == 2
    assert "there is no" in capsys.readouterr().err


def test_the_gate_fails_a_loose_project(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = tmp_path / "pyproject.toml"
    project.write_text(GOOD.replace("click==8.1.8", "click"), encoding="utf-8")
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(f"## {__version__}\n", encoding="utf-8")
    assert main(["--pyproject", str(project), "--changelog", str(changelog)]) == 1
    assert "not pinned exactly" in capsys.readouterr().err
