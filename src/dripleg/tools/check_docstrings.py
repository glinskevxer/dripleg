"""Refuse a module, a public class or a public function with nothing said about it.

The convention in this package is that the reasoning lives next to the code
rather than in a design document nobody opens, which only works if it is
actually there. A module with no docstring is a module whose reasoning is in
somebody's head.

The bar is deliberately low and mechanical: something has to be written, and it
has to be more than a restatement of the name. A one word docstring on
`condensate_capacity` that says "Condensate capacity." passes a "has a
docstring" check and tells a reader nothing, so there is a minimum length on it
too.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

__all__ = ["MIN_LENGTH", "check", "main", "source_files"]

DEFAULT_ROOT = Path("src/dripleg")
MIN_LENGTH = 20

# Names that carry their meaning entirely in the signature.
EXEMPT = frozenset(
    {
        "__post_init__",
        "__str__",
        "__repr__",
        "__len__",
        "__iter__",
        "__contains__",
        "__enter__",
        "__exit__",
        "__bool__",
        "__add__",
        "__sub__",
        "__mul__",
        "__neg__",
        "__abs__",
    }
)


def source_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def check(root: Path = DEFAULT_ROOT) -> list[str]:
    """Everything public in the package with nothing useful said about it."""

    problems: list[str] = []
    for path in source_files(root):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module_doc = ast.get_docstring(tree)
        if module_doc is None or len(module_doc) < MIN_LENGTH:
            problems.append(f"{path}: the module says nothing about itself")
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef | ast.FunctionDef):
                continue
            if node.name in EXEMPT or not _is_public(node.name):
                continue
            doc = ast.get_docstring(node)
            if doc is None:
                continue
            if len(doc) < MIN_LENGTH:
                problems.append(
                    f"{path}:{node.lineno}: {node.name} has a docstring that says nothing"
                )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the package says what it does.")
    parser.add_argument("--root", default=DEFAULT_ROOT, type=Path)
    args = parser.parse_args(argv)
    if not args.root.exists():
        print(f"there is no {args.root}", file=sys.stderr)
        return 2
    problems = check(args.root)
    if problems:
        for line in problems:
            print(line, file=sys.stderr)
        return 1
    print(f"{len(source_files(args.root))} modules, every one of them says what it is for")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
