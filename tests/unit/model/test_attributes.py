from __future__ import annotations

import pytest

from dripleg.errors import ValidationError
from dripleg.model.attributes import Accessibility, Criticality, ServiceType


def test_process_service_is_marked_as_process() -> None:
    assert ServiceType.PROCESS_COIL.is_process
    assert ServiceType.STERILISER.is_process
    assert not ServiceType.DRIP.is_process
    assert not ServiceType.TRACER.is_process


def test_load_varies_on_process_and_on_a_unit_heater() -> None:
    assert ServiceType.SHELL_AND_TUBE.condensate_load_varies
    assert ServiceType.UNIT_HEATER.condensate_load_varies
    assert not ServiceType.DRIP.condensate_load_varies


def test_the_services_where_a_blocked_trap_stops_the_job() -> None:
    assert ServiceType.TURBINE_DRAIN.failure_stops_production
    assert ServiceType.PROCESS_COIL.failure_stops_production
    assert not ServiceType.TRACER.failure_stops_production
    assert not ServiceType.SEPARATOR.failure_stops_production


def test_every_service_has_a_default_interval() -> None:
    for service in ServiceType:
        assert 6 <= service.survey_interval_months <= 24


def test_a_turbine_drain_is_looked_at_twice_as_often_as_a_drip() -> None:
    assert ServiceType.TURBINE_DRAIN.survey_interval_months == 6
    assert ServiceType.DRIP.survey_interval_months == 12
    assert ServiceType.TRACER.survey_interval_months == 24


def test_service_labels_read_like_english() -> None:
    assert ServiceType.SHELL_AND_TUBE.label == "shell and tube"


def test_access_multiplies_the_labour() -> None:
    assert Accessibility.GROUND_LEVEL.labour_multiplier == 1.0
    assert Accessibility.SCAFFOLD_REQUIRED.labour_multiplier > 3.0
    assert (
        Accessibility.SHUTDOWN_ONLY.labour_multiplier
        > Accessibility.CONFINED_SPACE.labour_multiplier
    )


def test_every_access_grade_costs_at_least_ground_level() -> None:
    for access in Accessibility:
        assert access.labour_multiplier >= 1.0


def test_the_permit_jobs() -> None:
    assert Accessibility.CONFINED_SPACE.needs_a_permit
    assert Accessibility.HOT_WORK_PERMIT.needs_a_permit
    assert not Accessibility.LADDER.needs_a_permit


def test_only_a_shutdown_job_cannot_be_done_running() -> None:
    assert Accessibility.CONFINED_SPACE.can_be_done_running
    assert not Accessibility.SHUTDOWN_ONLY.can_be_done_running


def test_what_a_technician_can_read_without_arranging_anything() -> None:
    assert Accessibility.GROUND_LEVEL.surveyable_on_a_normal_route
    assert Accessibility.LADDER.surveyable_on_a_normal_route
    assert not Accessibility.SCAFFOLD_REQUIRED.surveyable_on_a_normal_route
    assert not Accessibility.SHUTDOWN_ONLY.surveyable_on_a_normal_route


def test_criticality_weights_run_the_right_way_round() -> None:
    weights = [c.weight for c in Criticality]
    assert Criticality.SAFETY.weight == max(weights)
    assert Criticality.NUISANCE.weight == min(weights)


def test_only_safety_escalates_on_its_own() -> None:
    assert Criticality.SAFETY.escalates_immediately
    assert not Criticality.PRODUCTION.escalates_immediately


def test_criticality_parses_what_a_spreadsheet_holds() -> None:
    assert Criticality.parse(" Production ") is Criticality.PRODUCTION
    assert Criticality.parse("nuisance") is Criticality.NUISANCE


def test_criticality_refuses_what_it_does_not_know() -> None:
    with pytest.raises(ValidationError, match="not a criticality"):
        Criticality.parse("very important")
