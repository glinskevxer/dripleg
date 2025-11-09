from __future__ import annotations

import datetime as dt

import pytest

from dripleg.errors import DriplegError, ValidationError
from dripleg.ingest.register_reader import read_register_csv
from dripleg.model.attributes import Accessibility, Criticality, ServiceType
from dripleg.model.catalogue import TrapCatalogue
from dripleg.model.header import DischargeDestination
from dripleg.model.operating import OperatingProfile
from dripleg.model.tags import TrapTag
from tests.support.build import a_model, header_for

HEADERS = [header_for(TrapTag.parse("B12-MP-1")), header_for(TrapTag.parse("B12-LP-1"))]
CATALOGUE = TrapCatalogue([a_model()])
PROFILES = [OperatingProfile.continuous(), OperatingProfile("TRC", "Tracer", load_factor=0.4)]

FILE = (
    "tag,manufacturer,model,installed,service,access,criticality,profile,"
    "destination,strainer,valves,interval,note\n"
    "B12-MP-1,Halden,TD52,2021-06-14,drip,ground_level,nuisance,CONT,,y,2,,by the door\n"
    "B12-LP-1,Halden,TD52,2022-01-04,unit heater,ladder,comfort,TRC,atmosphere,n,1,3,\n"
)

MINIMAL = "tag,manufacturer,model,installed\nB12-MP-1,Halden,TD52,2021-06-14\n"


def read(text: str = FILE):  # type: ignore[no-untyped-def]
    return read_register_csv(text, "WRX1", HEADERS, CATALOGUE, PROFILES)


def test_a_register_reads_into_stations() -> None:
    result = read()
    assert result.read == 2
    assert result.is_clean
    assert [str(s.tag) for s in result.stations] == ["B12-MP-0001", "B12-LP-0001"]


def test_every_column_comes_through() -> None:
    second = read().stations[1]
    assert second.service is ServiceType.UNIT_HEATER
    assert second.accessibility is Accessibility.LADDER
    assert second.criticality is Criticality.COMFORT
    assert second.profile.code == "TRC"
    assert second.destination is DischargeDestination.ATMOSPHERE
    assert not second.strainer_fitted
    assert second.isolation_valves == 1
    assert second.interval_months_override == 3


def test_the_optional_columns_default_sensibly() -> None:
    station = read(MINIMAL).stations[0]
    assert station.service is ServiceType.DRIP
    assert station.accessibility is Accessibility.GROUND_LEVEL
    assert station.criticality is Criticality.NUISANCE
    assert station.profile.code == "CONT"
    assert station.destination is None
    assert station.strainer_fitted
    assert station.isolation_valves == 2
    assert station.installed_on == dt.date(2021, 6, 14)


def test_a_header_that_is_not_on_the_book_is_quarantined() -> None:
    text = MINIMAL.replace("B12-MP-1", "C3-MP-1")
    result = read(text)
    assert result.read == 0
    assert "no header" in result.quarantined[0].reason


def test_a_model_that_is_not_in_the_catalogue_is_quarantined() -> None:
    result = read(MINIMAL.replace("TD52", "NOPE"))
    assert "no trap model" in result.quarantined[0].reason


def test_a_profile_that_is_not_on_the_book_is_quarantined() -> None:
    text = MINIMAL.replace("installed\n", "installed,profile\n").replace(
        "2021-06-14\n", "2021-06-14,NOPE\n"
    )
    result = read(text)
    assert "no operating profile" in result.quarantined[0].reason


def test_a_bad_tag_is_quarantined_and_the_rest_goes_in() -> None:
    result = read(FILE.replace("B12-LP-1", "rubbish"))
    assert result.read == 1
    assert result.rejected == 1
    assert result.quarantined[0].line == 3


def test_a_bad_date_is_quarantined() -> None:
    result = read(MINIMAL.replace("2021-06-14", "14/06/2021"))
    assert result.rejected == 1
    assert "isoformat" in result.quarantined[0].reason.lower() or result.quarantined[0].reason


def test_a_bad_service_is_quarantined() -> None:
    text = MINIMAL.replace("installed\n", "installed,service\n").replace(
        "2021-06-14\n", "2021-06-14,steamy\n"
    )
    result = read(text)
    assert "is not a service" in result.quarantined[0].reason


def test_a_bad_flag_is_quarantined() -> None:
    text = MINIMAL.replace("installed\n", "installed,strainer\n").replace(
        "2021-06-14\n", "2021-06-14,maybe\n"
    )
    result = read(text)
    assert "is not a yes or a no" in result.quarantined[0].reason


def test_a_tag_twice_in_one_file_keeps_the_first() -> None:
    result = read(FILE + "B12-MP-1,Halden,TD52,2024-01-01,drip,,,,,,,,\n")
    assert result.read == 2
    assert "appears twice" in result.quarantined[0].reason


def test_a_file_missing_a_required_column_is_refused() -> None:
    with pytest.raises(ValidationError, match="does not have: installed"):
        read("tag,manufacturer,model\nB12-MP-1,Halden,TD52\n")


def test_a_file_with_no_header_is_refused() -> None:
    with pytest.raises(DriplegError, match="no header row"):
        read("")


def test_the_content_hash_follows_the_bytes() -> None:
    assert read().content_hash == read().content_hash
    assert read().content_hash != read(MINIMAL).content_hash


def test_the_columns_are_matched_case_insensitively() -> None:
    result = read(MINIMAL.upper().replace("HALDEN", "Halden"))
    assert result.read == 1


def test_printing_a_result() -> None:
    assert str(read()) == "2 stations read, 0 quarantined"
