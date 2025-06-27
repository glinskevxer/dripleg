"""Fixtures every test layer shares."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.support import leaks

leaks.install()


@pytest.fixture(autouse=True)
def no_leaked_connections(request: pytest.FixtureRequest) -> Iterator[None]:
    """Fail a test that leaves a book open behind it."""

    label = request.node.nodeid
    leaks.TRACKER.working_on(label)
    yield
    leaks.TRACKER.working_on("teardown")
    found = leaks.TRACKER.leaked_here(label)
    if found:
        leaks.TRACKER.forget(label)
        pytest.fail("\n".join(found))
