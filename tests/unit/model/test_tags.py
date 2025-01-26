from __future__ import annotations

import pytest

from dripleg.errors import ValidationError
from dripleg.model.tags import AreaCode, SiteCode, SystemCode, TrapTag


def test_a_site_code_is_letters_and_digits() -> None:
    assert str(SiteCode.parse("wrx1")) == "WRX1"
    assert SiteCode.parse(" wrx1 ").value == "WRX1"


def test_a_site_code_starts_with_a_letter() -> None:
    for bad in ("1WRX", "", "  ", "WAYTOOLONGCODE", "WR-X"):
        with pytest.raises(ValidationError, match="site"):
            SiteCode.parse(bad)


def test_area_and_system_codes_normalise_the_same_way() -> None:
    assert str(AreaCode.parse("b12")) == "B12"
    assert str(SystemCode.parse("lp")) == "LP"
    with pytest.raises(ValidationError, match="area"):
        AreaCode.parse("TOOLONGAREA")
    with pytest.raises(ValidationError, match="system"):
        SystemCode.parse("9LP")


def test_a_tag_parses_into_its_parts() -> None:
    tag = TrapTag.parse("B12-LP-43")
    assert tag.area == AreaCode("B12")
    assert tag.system == SystemCode("LP")
    assert tag.sequence == 43


def test_a_tag_prints_zero_padded() -> None:
    assert str(TrapTag.parse("B12-LP-43")) == "B12-LP-0043"
    assert str(TrapTag.parse("b12-lp-0043")) == "B12-LP-0043"


def test_padding_on_the_way_in_does_not_change_the_tag() -> None:
    assert TrapTag.parse("B12-LP-43") == TrapTag.parse("B12-LP-0043")


def test_the_tablet_and_the_drawing_office_write_it_differently() -> None:
    assert TrapTag.parse("b12_lp_43") == TrapTag.parse("B12/LP/0043")
    assert TrapTag.parse(" B12 - LP - 43 ") == TrapTag.parse("B12-LP-43")


def test_a_tag_that_is_not_a_tag() -> None:
    for bad in ("B12-LP", "B12-LP-", "B12--43", "LP-43", "B12-LP-ABC", "B12-LP-1234567"):
        with pytest.raises(ValidationError, match="trap tag"):
            TrapTag.parse(bad)


def test_a_sequence_starts_at_one() -> None:
    with pytest.raises(ValidationError, match="starts at one"):
        TrapTag.of("B12", "LP", 0)
    with pytest.raises(ValidationError, match="stops at"):
        TrapTag.of("B12", "LP", 1000000)


def test_of_takes_loose_strings() -> None:
    assert TrapTag.of("b12", "lp", 43) == TrapTag.parse("B12-LP-43")


def test_the_next_tag_on_the_same_system() -> None:
    tag = TrapTag.parse("B12-LP-43")
    assert str(tag.next_in_sequence()) == "B12-LP-0044"
    assert tag.next_in_sequence().in_same_system_as(tag)


def test_tags_on_different_systems_are_not_the_same_system() -> None:
    assert not TrapTag.parse("B12-LP-1").in_same_system_as(TrapTag.parse("B12-HP-1"))
    assert not TrapTag.parse("B12-LP-1").in_same_system_as(TrapTag.parse("C3-LP-1"))


def test_the_prefix_groups_a_report() -> None:
    assert TrapTag.parse("B12-LP-43").prefix == "B12-LP"


def test_tags_sort_by_area_then_system_then_number() -> None:
    tags = [
        TrapTag.parse("C3-LP-2"),
        TrapTag.parse("B12-MP-1"),
        TrapTag.parse("B12-LP-10"),
        TrapTag.parse("B12-LP-2"),
    ]
    assert [str(t) for t in sorted(tags)] == [
        "B12-LP-0002",
        "B12-LP-0010",
        "B12-MP-0001",
        "C3-LP-0002",
    ]


def test_a_tag_is_hashable_so_it_can_key_a_register() -> None:
    register = {TrapTag.parse("B12-LP-43"): "thermodynamic"}
    assert register[TrapTag.parse("b12-lp-0043")] == "thermodynamic"


def test_repr_shows_the_printed_form() -> None:
    assert repr(TrapTag.parse("B12-LP-43")) == "TrapTag('B12-LP-0043')"
