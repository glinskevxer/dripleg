from __future__ import annotations

import pytest

from dripleg.errors import ValidationError
from dripleg.model.plant import Area, Site
from dripleg.model.tags import AreaCode, SiteCode


def make_site() -> Site:
    return Site.of("WRX1", "Wrexham paper mill", "Bryn Paper Holdings")


def test_a_site_holds_its_code_as_a_code() -> None:
    site = make_site()
    assert site.code == SiteCode("WRX1")
    assert str(site) == "WRX1 Wrexham paper mill"


def test_a_site_name_is_squeezed() -> None:
    site = Site.of("WRX1", "  Wrexham   paper  mill ", "Bryn")
    assert site.name == "Wrexham paper mill"


def test_a_blank_name_or_operator_is_refused() -> None:
    with pytest.raises(ValidationError, match="name cannot be blank"):
        Site.of("WRX1", "   ", "Bryn")
    with pytest.raises(ValidationError, match="operator cannot be blank"):
        Site.of("WRX1", "Mill", "")


def test_a_very_long_name_is_refused() -> None:
    with pytest.raises(ValidationError, match="longer than"):
        Site.of("WRX1", "x" * 81, "Bryn")


def test_the_programme_month_decides_the_calendar_question() -> None:
    assert make_site().runs_a_calendar_programme
    assert not Site.of("WRX1", "Mill", "Bryn", programme_start_month=4).runs_a_calendar_programme


def test_the_programme_month_is_a_month() -> None:
    with pytest.raises(ValidationError, match="starts in a month"):
        Site.of("WRX1", "Mill", "Bryn", programme_start_month=0)
    with pytest.raises(ValidationError, match="starts in a month"):
        Site.of("WRX1", "Mill", "Bryn", programme_start_month=13)


def test_the_fuel_basis_has_to_say_something() -> None:
    with pytest.raises(ValidationError, match="what the fuel price is for"):
        Site.of("WRX1", "Mill", "Bryn", fuel_price_basis="  ")


def test_an_area_carries_a_cost_centre() -> None:
    area = Area.of("WRX1", "B12", "Number 2 paper machine", "pm2-utilities")
    assert area.cost_centre == "PM2-UTILITIES"
    assert area.code == AreaCode("B12")
    assert str(area) == "WRX1/B12 Number 2 paper machine"


def test_an_area_without_a_cost_centre_is_refused() -> None:
    with pytest.raises(ValidationError, match="needs a cost centre"):
        Area.of("WRX1", "B12", "Machine", "   ")


def test_a_top_level_area_has_no_parent() -> None:
    assert Area.of("WRX1", "B12", "Machine", "CC1").is_top_level


def test_a_nested_area_names_its_parent() -> None:
    area = Area.of("WRX1", "B12A", "Dryer section", "CC1", parent="B12")
    assert not area.is_top_level
    assert area.parent == AreaCode("B12")


def test_an_area_cannot_be_its_own_parent() -> None:
    with pytest.raises(ValidationError, match="own parent"):
        Area.of("WRX1", "B12", "Machine", "CC1", parent="B12")


def test_an_area_knows_which_site_it_belongs_to() -> None:
    site = make_site()
    assert Area.of("WRX1", "B12", "Machine", "CC1").belongs_to(site)
    assert not Area.of("WRX2", "B12", "Machine", "CC1").belongs_to(site)


def test_the_area_key_is_site_and_code() -> None:
    assert Area.of("WRX1", "B12", "Machine", "CC1").key == ("WRX1", "B12")


def test_areas_are_hashable_and_compare_by_value() -> None:
    first = Area.of("WRX1", "B12", "Machine", "CC1")
    second = Area.of("wrx1", "b12", "Machine", "cc1")
    assert first == second
    assert len({first, second}) == 1
