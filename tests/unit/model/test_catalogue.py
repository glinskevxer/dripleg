from __future__ import annotations

import math

import pytest

from dripleg.errors import ConflictError, NotFoundError, ValidationError
from dripleg.model.catalogue import ConnectionType, TrapCatalogue, TrapModel
from dripleg.model.header import SteamHeader
from dripleg.model.plant import Area
from dripleg.model.principles import OperatingPrinciple
from dripleg.units.money import Money
from dripleg.units.pressure import Pressure


def model(
    code: str = "TD52",
    *,
    manufacturer: str = "Halden",
    principle: OperatingPrinciple = OperatingPrinciple.THERMODYNAMIC_DISC,
    orifice: float = 0.093,
    pmo_psig: float = 600.0,
    back_pressure: float = 80.0,
    price: str = "184.00",
    discontinued: bool = False,
    replaced_by: str | None = None,
) -> TrapModel:
    return TrapModel(
        manufacturer=manufacturer,
        code=code,
        principle=principle,
        orifice_diameter_in=orifice,
        max_operating_pressure=Pressure.from_psig(pmo_psig),
        max_back_pressure_percent=back_pressure,
        connection_size_in=0.5,
        connection_type=ConnectionType.SCREWED,
        list_price=Money.from_dollars(price),
        discontinued=discontinued,
        replaced_by=replaced_by,
    )


def header(operating: float = 125.0, discharge: float = 15.0) -> SteamHeader:
    area = Area.of("WRX1", "B12", "Number 2 paper machine", "PM2")
    return SteamHeader.of(area, "MP", "Main", operating, discharge_psig=discharge)


def test_a_model_normalises_its_code_and_maker() -> None:
    entry = model(code=" td52 ", manufacturer="  Halden   Valve ")
    assert entry.code == "TD52"
    assert entry.manufacturer == "HALDEN VALVE"
    assert entry.key == ("HALDEN VALVE", "TD52")


def test_the_orifice_area_is_the_circle() -> None:
    entry = model(orifice=0.1)
    assert entry.orifice_area_sq_in == pytest.approx(math.pi * 0.0025)


def test_a_model_refuses_rubbish() -> None:
    with pytest.raises(ValidationError, match="needs a manufacturer"):
        model(manufacturer="  ")
    with pytest.raises(ValidationError, match="not a model code"):
        model(code="a")
    with pytest.raises(ValidationError, match="not a trap orifice"):
        model(orifice=3.0)
    with pytest.raises(ValidationError, match="not a trap orifice"):
        model(orifice=0.0)
    with pytest.raises(ValidationError, match="percentage of inlet"):
        model(back_pressure=140.0)


def test_a_model_checks_its_connection() -> None:
    with pytest.raises(ValidationError, match="not a connection"):
        TrapModel(
            manufacturer="Halden",
            code="TD52",
            principle=OperatingPrinciple.THERMODYNAMIC_DISC,
            orifice_diameter_in=0.093,
            max_operating_pressure=Pressure.from_psig(600.0),
            max_back_pressure_percent=80.0,
            connection_size_in=0.5,
            connection_type="glued",
            list_price=Money.from_dollars("100"),
        )


def test_a_connection_needs_a_size() -> None:
    with pytest.raises(ValidationError, match="a connection has a size"):
        TrapModel(
            manufacturer="Halden",
            code="TD52",
            principle=OperatingPrinciple.THERMODYNAMIC_DISC,
            orifice_diameter_in=0.093,
            max_operating_pressure=Pressure.from_psig(600.0),
            max_back_pressure_percent=80.0,
            connection_size_in=0.0,
            connection_type=ConnectionType.SCREWED,
            list_price=Money.from_dollars("100"),
        )


def test_pressure_and_back_pressure_limits() -> None:
    entry = model(pmo_psig=200.0, back_pressure=50.0)
    assert entry.suits_pressure(Pressure.from_psig(150.0))
    assert not entry.suits_pressure(Pressure.from_psig(250.0))
    limit = entry.back_pressure_limit_at(Pressure.from_psig(125.0))
    assert limit.psia == pytest.approx(139.696 * 0.5, abs=0.01)


def test_a_model_suits_a_header_only_if_both_limits_hold() -> None:
    assert model(pmo_psig=600.0, back_pressure=80.0).suits_header(header())
    assert not model(pmo_psig=100.0).suits_header(header())
    assert not model(back_pressure=10.0).suits_header(header())


def test_only_a_discontinued_model_names_a_replacement() -> None:
    with pytest.raises(ValidationError, match="only a discontinued"):
        model(replaced_by="TD60")
    with pytest.raises(ValidationError, match="cannot replace itself"):
        model(discontinued=True, replaced_by="td52")
    assert not model(discontinued=True).is_orderable()


def test_the_catalogue_keys_on_maker_and_code() -> None:
    book = TrapCatalogue(
        [model("TD52"), model("IB18", principle=OperatingPrinciple.INVERTED_BUCKET)]
    )
    assert len(book) == 2
    assert book.get("halden", "td52").code == "TD52"
    assert ("HALDEN", "IB18") in book


def test_the_catalogue_refuses_a_duplicate() -> None:
    book = TrapCatalogue([model("TD52")])
    with pytest.raises(ConflictError, match="already in the catalogue"):
        book.add(model("td52"))


def test_a_missing_model_raises_and_find_does_not() -> None:
    book = TrapCatalogue([model("TD52")])
    with pytest.raises(NotFoundError, match="trap model"):
        book.get("Halden", "NOPE")
    assert book.find("Halden", "NOPE") is None


def test_filtering_by_principle() -> None:
    book = TrapCatalogue(
        [
            model("TD52"),
            model("TD75"),
            model("FT40", principle=OperatingPrinciple.FLOAT_THERMOSTATIC),
        ]
    )
    discs = book.with_principle(OperatingPrinciple.THERMODYNAMIC_DISC)
    assert [m.code for m in discs] == ["TD52", "TD75"]
    assert len(book.with_principle(OperatingPrinciple.VENTURI)) == 0


def test_what_could_go_on_a_header_comes_back_cheapest_first() -> None:
    book = TrapCatalogue(
        [
            model("TD52", price="184.00"),
            model("TD75", price="96.50"),
            model("LP10", pmo_psig=50.0, price="40.00"),
            model("OLD1", price="10.00", discontinued=True),
        ]
    )
    fits = book.orderable_for(header())
    assert [m.code for m in fits] == ["TD75", "TD52"]


def test_a_discontinued_model_leads_to_its_successor() -> None:
    book = TrapCatalogue(
        [
            model("TD52", discontinued=True, replaced_by="TD60"),
            model("TD60", discontinued=True, replaced_by="TD75"),
            model("TD75"),
        ]
    )
    assert book.successor_of(book.get("Halden", "TD52")).code == "TD75"  # type: ignore[union-attr]
    assert book.successor_of(book.get("Halden", "TD75")) is None


def test_a_replacement_chain_that_goes_nowhere() -> None:
    book = TrapCatalogue([model("TD52", discontinued=True, replaced_by="TD99")])
    assert book.successor_of(book.get("Halden", "TD52")) is None


def test_a_replacement_chain_that_loops_is_caught() -> None:
    book = TrapCatalogue(
        [
            model("TD52", discontinued=True, replaced_by="TD60"),
            model("TD60", discontinued=True, replaced_by="TD52"),
        ]
    )
    with pytest.raises(ConflictError, match="loops"):
        book.successor_of(book.get("Halden", "TD52"))


def test_iterating_the_catalogue_is_sorted() -> None:
    book = TrapCatalogue([model("TD75"), model("IB18"), model("FT40")])
    assert [m.code for m in book] == ["FT40", "IB18", "TD75"]


def test_printing_a_model() -> None:
    assert str(model()) == "HALDEN TD52 (0.093 in)"
