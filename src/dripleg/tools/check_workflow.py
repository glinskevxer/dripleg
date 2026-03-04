"""Hold the CI workflow and the tools in this package to each other.

Two failures, both of which have happened here.

A tool gets written, tested, and never wired into CI, so it passes forever and
guards nothing. The suite is green, the gate is not running, and nobody finds
out until the thing it was supposed to catch gets through.

The other way round, a CI step names a module that has been renamed. That one
announces itself the first time CI runs, which is better, but only if CI runs
before somebody spends an afternoon wondering why the job is red.

So this reads the workflow as text, pulls out every `python -m dripleg.tools.x`
it runs, and checks the set against what is actually in the tools package. It
deliberately does not parse yaml: the workflow is read here exactly as a person
reads it, and a step hidden behind a yaml anchor is a step that should not be
hidden.
"""

from __future__ import annotations

import argparse
import importlib
import pkgutil
import re
import sys
from pathlib import Path

import dripleg.tools

__all__ = ["DEFAULT_WORKFLOW", "check", "tool_modules", "wired_modules"]

DEFAULT_WORKFLOW = Path(".github/workflows/ci.yml")

# Tools that are not gates and are not expected to run in CI.
NOT_A_GATE = frozenset({"__init__"})

_STEP = re.compile(r"python -m dripleg\.tools\.(?P<name>[a-z_]+)")


def tool_modules() -> set[str]:
    """Every module in the tools package."""

    return {
        module.name
        for module in pkgutil.iter_modules(dripleg.tools.__path__)
        if module.name not in NOT_A_GATE
    }


def wired_modules(workflow: str) -> set[str]:
    """Every tool the workflow runs."""

    return {match.group("name") for match in _STEP.finditer(workflow)}


def check(workflow: str) -> list[str]:
    """Everything out of step between the workflow and the tools package."""

    present = tool_modules()
    wired = wired_modules(workflow)
    problems: list[str] = []
    for name in sorted(wired - present):
        problems.append(f"the workflow runs dripleg.tools.{name}, which is not there")
    for name in sorted(present - wired):
        problems.append(f"dripleg.tools.{name} is not run by the workflow")
    for name in sorted(present & wired):
        module = importlib.import_module(f"dripleg.tools.{name}")
        if not hasattr(module, "main"):
            problems.append(f"dripleg.tools.{name} has no main to run")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check CI runs every gate in this build.")
    parser.add_argument("--workflow", default=DEFAULT_WORKFLOW, type=Path)
    args = parser.parse_args(argv)
    if not args.workflow.exists():
        print(f"there is no workflow at {args.workflow}", file=sys.stderr)
        return 2
    problems = check(args.workflow.read_text(encoding="utf-8"))
    if problems:
        for line in problems:
            print(line, file=sys.stderr)
        return 1
    print(f"{len(tool_modules())} tools, all of them run by the workflow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
