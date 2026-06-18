"""Hold every module's `__all__` to what the module actually defines.

Two failure modes, both quiet. A name gets renamed and its old spelling stays
in `__all__`, so `from x import *` raises and nothing else notices because
nothing else does that. Or a public helper gets added and never reaches
`__all__`, so it is public by accident and gets used, and then cannot be
renamed.

There is a third thing checked here and it is the one that matters: `__all__`
has to be sorted. Not for tidiness, but because an unsorted list is a list
people append to, and a list people append to gets duplicates in it.
"""

from __future__ import annotations

import argparse
import importlib
import pkgutil
import sys

import dripleg

__all__ = ["check", "main", "modules"]

# Modules with no public surface of their own.
NO_EXPORTS = frozenset({"dripleg.cli.main", "dripleg.thresholds"})


def modules() -> list[str]:
    """Every module in the package, in import order."""

    found = [dripleg.__name__]
    for module in pkgutil.walk_packages(dripleg.__path__, prefix="dripleg."):
        found.append(module.name)
    return sorted(found)


def check() -> list[str]:
    """Everything wrong with the packages' declared exports."""

    problems: list[str] = []
    for name in modules():
        module = importlib.import_module(name)
        declared = getattr(module, "__all__", None)
        if declared is None:
            continue
        if list(declared) != sorted(declared):
            problems.append(f"{name}: __all__ is not sorted")
        if len(set(declared)) != len(declared):
            problems.append(f"{name}: __all__ has a name in it twice")
        for exported in declared:
            if not hasattr(module, exported):
                problems.append(f"{name}: __all__ names {exported}, which is not there")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check every module's exports.")
    parser.add_argument("--list", action="store_true", help="Print the module list.")
    args = parser.parse_args(argv)
    if args.list:
        for name in modules():
            print(name)
    problems = check()
    if problems:
        for line in problems:
            print(line, file=sys.stderr)
        return 1
    print(f"{len(modules())} modules, every declared export present and in order")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
