from __future__ import annotations

from pathlib import Path

import pytest

from dripleg.tools.check_docstrings import MIN_LENGTH, check, main, source_files


def test_this_package_says_what_it_does() -> None:
    assert check() == []


def test_every_source_file_is_looked_at() -> None:
    paths = [str(path) for path in source_files(Path("src/dripleg"))]
    assert "src/dripleg/units/pressure.py" in paths
    assert "src/dripleg/cli/main.py" in paths
    assert not any("__pycache__" in path for path in paths)


def test_a_module_with_no_docstring_is_caught(tmp_path: Path) -> None:
    (tmp_path / "bare.py").write_text("x = 1\n", encoding="utf-8")
    problems = check(tmp_path)
    assert problems == [f"{tmp_path / 'bare.py'}: the module says nothing about itself"]


def test_a_one_word_module_docstring_is_caught(tmp_path: Path) -> None:
    (tmp_path / "thin.py").write_text('"""Traps."""\n', encoding="utf-8")
    assert check(tmp_path) == [f"{tmp_path / 'thin.py'}: the module says nothing about itself"]


def test_a_thin_function_docstring_is_caught(tmp_path: Path) -> None:
    (tmp_path / "thin.py").write_text(
        '"""A module that says something about itself."""\n\n'
        'def capacity() -> int:\n    """Capacity."""\n    return 1\n',
        encoding="utf-8",
    )
    problems = check(tmp_path)
    assert len(problems) == 1
    assert "capacity has a docstring that says nothing" in problems[0]


def test_a_private_function_is_left_alone(tmp_path: Path) -> None:
    (tmp_path / "quiet.py").write_text(
        '"""A module that says something about itself."""\n\n'
        'def _capacity() -> int:\n    """Cap."""\n    return 1\n',
        encoding="utf-8",
    )
    assert check(tmp_path) == []


def test_a_dunder_with_a_short_docstring_is_left_alone(tmp_path: Path) -> None:
    (tmp_path / "dunder.py").write_text(
        '"""A module that says something about itself."""\n\n'
        'class Thing:\n    """A thing worth saying something about."""\n\n'
        '    def __str__(self) -> str:\n        """Print."""\n        return "x"\n',
        encoding="utf-8",
    )
    assert check(tmp_path) == []


def test_a_function_with_no_docstring_at_all_is_left_alone(tmp_path: Path) -> None:
    """The bar is on what is written, not on writing something everywhere."""

    (tmp_path / "plain.py").write_text(
        '"""A module that says something about itself."""\n\n'
        "def capacity() -> int:\n    return 1\n",
        encoding="utf-8",
    )
    assert check(tmp_path) == []


def test_the_minimum_is_short_enough_to_be_reasonable() -> None:
    assert 10 <= MIN_LENGTH <= 40


def test_the_gate_passes_on_this_build(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "says what it is for" in capsys.readouterr().out


def test_the_gate_fails_a_bare_module(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "bare.py").write_text("x = 1\n", encoding="utf-8")
    assert main(["--root", str(tmp_path)]) == 1
    assert "says nothing about itself" in capsys.readouterr().err


def test_a_root_that_is_not_there(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--root", str(tmp_path / "nope")]) == 2
    assert "there is no" in capsys.readouterr().err
