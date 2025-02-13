from __future__ import annotations

import pytest

from dripleg.errors import ValidationError
from dripleg.model.principles import (
    PRINCIPLES,
    DischargePattern,
    FailureTendency,
    OperatingPrinciple,
    PrincipleProfile,
)


def test_every_principle_has_a_profile() -> None:
    for principle in OperatingPrinciple:
        assert principle.profile.principle is principle
    assert set(PRINCIPLES) == set(OperatingPrinciple)


def test_a_disc_trap_cycles_and_fails_open() -> None:
    profile = OperatingPrinciple.THERMODYNAMIC_DISC.profile
    assert profile.pattern is DischargePattern.INTERMITTENT
    assert profile.tendency is FailureTendency.OPEN
    assert profile.sound_carries_upstream


def test_a_float_trap_runs_continuous_and_fails_closed() -> None:
    profile = OperatingPrinciple.FLOAT_THERMOSTATIC.profile
    assert profile.pattern is DischargePattern.CONTINUOUS
    assert profile.tendency is FailureTendency.CLOSED
    assert not profile.pattern.is_audible_cycling


def test_a_bimetallic_trap_backs_condensate_up_a_long_way() -> None:
    profile = OperatingPrinciple.BIMETALLIC.profile
    assert profile.holds_condensate_back
    assert profile.subcooling_f == (20.0, 90.0)
    assert not profile.discharges_at_saturation


def test_a_disc_trap_discharges_at_saturation() -> None:
    assert OperatingPrinciple.THERMODYNAMIC_DISC.profile.discharges_at_saturation
    assert not OperatingPrinciple.BALANCED_PRESSURE.profile.discharges_at_saturation


def test_a_normal_cycle_rate_for_a_cycling_trap_has_a_floor() -> None:
    profile = OperatingPrinciple.THERMODYNAMIC_DISC.profile
    assert profile.cycle_rate_is_normal(3.0)
    assert not profile.cycle_rate_is_normal(12.0)
    assert not profile.cycle_rate_is_normal(0.1)


def test_a_continuous_trap_has_no_floor_on_its_cycle_rate() -> None:
    profile = OperatingPrinciple.FLOAT_THERMOSTATIC.profile
    assert profile.cycle_rate_is_normal(0.0)
    assert not profile.cycle_rate_is_normal(4.0)


def test_subcooling_is_judged_against_the_principle() -> None:
    thermostatic = OperatingPrinciple.BALANCED_PRESSURE.profile
    assert thermostatic.subcooling_is_normal(25.0)
    assert not thermostatic.subcooling_is_normal(2.0)
    disc = OperatingPrinciple.THERMODYNAMIC_DISC.profile
    assert disc.subcooling_is_normal(2.0)
    assert not disc.subcooling_is_normal(25.0)


def test_the_orifice_types_look_the_same_and_are_written_down_that_way() -> None:
    orifice = OperatingPrinciple.FIXED_ORIFICE.profile
    venturi = OperatingPrinciple.VENTURI.profile
    assert orifice.pattern is venturi.pattern
    assert orifice.tendency is venturi.tendency is FailureTendency.OPEN


def test_labels_read_like_english() -> None:
    assert OperatingPrinciple.FLOAT_THERMOSTATIC.label == "float thermostatic"
    assert OperatingPrinciple.INVERTED_BUCKET.label == "inverted bucket"


def test_every_profile_says_why() -> None:
    for principle in OperatingPrinciple:
        assert len(principle.profile.note) > 20


def test_a_backwards_cycle_band_is_refused() -> None:
    with pytest.raises(ValidationError, match="cycle rate band"):
        PrincipleProfile(
            principle=OperatingPrinciple.VENTURI,
            pattern=DischargePattern.CONTINUOUS,
            tendency=FailureTendency.OPEN,
            cycles_per_minute=(4.0, 1.0),
            subcooling_f=(0.0, 5.0),
            holds_condensate_back=False,
            sound_carries_upstream=False,
            note="a note that is long enough to pass the check",
        )


def test_a_backwards_subcooling_band_is_refused() -> None:
    with pytest.raises(ValidationError, match="subcooling band"):
        PrincipleProfile(
            principle=OperatingPrinciple.VENTURI,
            pattern=DischargePattern.CONTINUOUS,
            tendency=FailureTendency.OPEN,
            cycles_per_minute=(0.0, 1.0),
            subcooling_f=(50.0, 5.0),
            holds_condensate_back=False,
            sound_carries_upstream=False,
            note="a note that is long enough to pass the check",
        )


def test_a_profile_without_a_reason_is_refused() -> None:
    with pytest.raises(ValidationError, match="why the numbers"):
        PrincipleProfile(
            principle=OperatingPrinciple.VENTURI,
            pattern=DischargePattern.CONTINUOUS,
            tendency=FailureTendency.OPEN,
            cycles_per_minute=(0.0, 1.0),
            subcooling_f=(0.0, 5.0),
            holds_condensate_back=False,
            sound_carries_upstream=False,
            note="   ",
        )


def test_only_the_cycling_patterns_are_audible() -> None:
    assert DischargePattern.INTERMITTENT.is_audible_cycling
    assert DischargePattern.CYCLIC.is_audible_cycling
    assert not DischargePattern.CONTINUOUS.is_audible_cycling
    assert not DischargePattern.MODULATING.is_audible_cycling
