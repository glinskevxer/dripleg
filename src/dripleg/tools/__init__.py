"""The gates this build holds itself to, each one runnable on its own.

Every module in here is a command with a `main`, every one of them is run by
CI, and `check_workflow` refuses a build where those two statements stop being
true. They are here rather than in a scripts directory so that they ship inside
the wheel and can be run against an installed copy.
"""

from __future__ import annotations

__all__: list[str] = []
