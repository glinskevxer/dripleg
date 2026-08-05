from __future__ import annotations

from pathlib import Path

import pytest

from dripleg.tools.check_workflow import (
    DEFAULT_WORKFLOW,
    check,
    main,
    tool_modules,
    wired_modules,
)


def test_the_tools_package_is_found() -> None:
    names = tool_modules()
    assert "coverage_gate" in names
    assert "check_migrations" in names
    assert "__init__" not in names


def test_the_workflow_in_this_build_runs_every_tool() -> None:
    assert DEFAULT_WORKFLOW.exists()
    assert check(DEFAULT_WORKFLOW.read_text(encoding="utf-8")) == []


def test_the_steps_are_pulled_out_of_the_text() -> None:
    workflow = """
    jobs:
      lint:
        steps:
          - run: python -m dripleg.tools.check_migrations
          - run: python -m dripleg.tools.schema_dump --check
    """
    assert wired_modules(workflow) == {"check_migrations", "schema_dump"}


def test_a_workflow_running_nothing_names_every_tool() -> None:
    problems = check("jobs:\n  lint:\n    steps:\n      - run: python -m pytest\n")
    assert len(problems) == len(tool_modules())
    assert all("is not run by the workflow" in line for line in problems)


def test_a_workflow_running_something_that_is_gone_is_caught() -> None:
    workflow = "\n".join(
        f"      - run: python -m dripleg.tools.{name}" for name in sorted(tool_modules())
    )
    workflow += "\n      - run: python -m dripleg.tools.long_gone"
    problems = check(workflow)
    assert problems == ["the workflow runs dripleg.tools.long_gone, which is not there"]


def test_every_tool_has_a_main_to_run() -> None:
    workflow = "\n".join(
        f"      - run: python -m dripleg.tools.{name}" for name in sorted(tool_modules())
    )
    assert check(workflow) == []


def test_the_gate_passes_on_this_build(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "all of them run by the workflow" in capsys.readouterr().out


def test_the_gate_fails_a_workflow_that_misses_a_gate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    workflow = tmp_path / "ci.yml"
    workflow.write_text("steps:\n  - run: python -m pytest\n", encoding="utf-8")
    assert main(["--workflow", str(workflow)]) == 1
    assert "is not run by the workflow" in capsys.readouterr().err


def test_a_workflow_that_is_not_there_is_a_different_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--workflow", str(tmp_path / "nope.yml")]) == 2
    assert "there is no workflow" in capsys.readouterr().err


def test_the_check_is_stable() -> None:
    text = DEFAULT_WORKFLOW.read_text(encoding="utf-8")
    assert check(text) == check(text)


def test_the_workflow_runs_the_release_check() -> None:
    text = DEFAULT_WORKFLOW.read_text(encoding="utf-8")
    assert "dripleg.tools.release_check" in text


def test_the_workflow_installs_the_wheel_and_walks_it() -> None:
    text = DEFAULT_WORKFLOW.read_text(encoding="utf-8")
    assert "installed-walk:" in text
    assert 'dripleg --book "$book" survey import' in text
    assert 'dripleg --book "$book" loss report' in text


def test_every_command_the_walk_runs_is_a_real_command() -> None:
    import re

    from dripleg.cli.main import cli

    text = DEFAULT_WORKFLOW.read_text(encoding="utf-8")
    used = set(re.findall(r'dripleg --book "\$book" ([a-z-]+)(?: ([a-z-]+))?', text))
    for group, command in used:
        assert group in cli.commands, group
        found = cli.commands[group]
        if command and hasattr(found, "commands"):
            assert command in found.commands, f"{group} {command}"


def test_the_package_job_uploads_what_it_built() -> None:
    text = DEFAULT_WORKFLOW.read_text(encoding="utf-8")
    assert "upload-artifact@v4" in text
    assert "name: dist" in text


def test_the_walk_uses_the_console_script_not_the_module() -> None:
    """The installed entry point is the thing under test, so it has to be used."""

    text = DEFAULT_WORKFLOW.read_text(encoding="utf-8")
    walk = text.split("installed-walk:", 1)[1]
    assert "python -m dripleg.cli" not in walk
    assert "dripleg --book" in walk


def test_the_walk_runs_under_a_strict_shell() -> None:
    text = DEFAULT_WORKFLOW.read_text(encoding="utf-8")
    walk = text.split("installed-walk:", 1)[1]
    assert "set -euo pipefail" in walk
