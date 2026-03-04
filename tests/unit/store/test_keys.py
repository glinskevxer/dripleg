from __future__ import annotations

import datetime as dt

import pytest

from dripleg.errors import ValidationError
from dripleg.model.tags import AreaCode, SiteCode, SystemCode, TrapTag
from dripleg.store.keys import as_area, as_date, as_site, as_system, as_tag, maybe_date


def test_a_site_comes_through_either_way() -> None:
    code = SiteCode("WRX1")
    assert as_site(code) is code
    assert as_site("wrx1") == code


def test_an_area_and_a_system_come_through_either_way() -> None:
    assert as_area("b12") == AreaCode("B12")
    assert as_area(AreaCode("B12")) == AreaCode("B12")
    assert as_system("mp") == SystemCode("MP")
    assert as_system(SystemCode("MP")) == SystemCode("MP")


def test_a_tag_comes_through_either_way() -> None:
    tag = TrapTag.parse("B12-MP-43")
    assert as_tag(tag) is tag
    assert as_tag("b12-mp-0043") == tag


def test_a_bad_string_still_raises() -> None:
    with pytest.raises(ValidationError, match="site"):
        as_site("1234")
    with pytest.raises(ValidationError, match="trap tag"):
        as_tag("nonsense")


def test_a_date_reads_off_a_text_column() -> None:
    assert as_date("2025-04-08") == dt.date(2025, 4, 8)
    assert as_date(dt.date(2025, 4, 8)) == dt.date(2025, 4, 8)


def test_a_bad_date_raises() -> None:
    with pytest.raises(ValueError, match="isoformat"):
        as_date("08/04/2025")


def test_a_null_date_column_comes_back_as_none() -> None:
    assert maybe_date(None) is None
    assert maybe_date("2025-04-08") == dt.date(2025, 4, 8)


def test_no_repository_writes_the_coercion_out_by_hand() -> None:
    """The whole point of this module, held in place by a test."""

    from pathlib import Path

    store = Path("src/dripleg/store")
    offenders = []
    for path in sorted(store.glob("*.py")):
        if path.name == "keys.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "isinstance(site, SiteCode)" in text or "isinstance(tag, TrapTag)" in text:
            offenders.append(path.name)
    assert offenders == []
