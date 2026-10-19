"""Distribute bindings: split strategies and the envelope guard."""

import pytest
from pydantic import ValidationError

from src.shared.schemas.template import (
    DistributeBinding,
)


def test_binding_distribute_equal_split() -> None:
    # Arrange / Act
    b = DistributeBinding(protocol="distribute", allocation_policy="equal_split")
    # Assert
    assert b.allocation_policy == "equal_split"


def test_binding_distribute_soc_weighted() -> None:
    # Arrange / Act
    b = DistributeBinding(protocol="distribute", allocation_policy="soc_weighted")
    # Assert
    assert b.allocation_policy == "soc_weighted"


def test_binding_distribute_envelope_guard() -> None:
    # Arrange / Act — control-law numbers, all three present
    b = DistributeBinding(
        protocol="distribute",
        allocation_policy="soc_weighted",
        ramp_rate_per_sec=0.10,
        hysteresis_margin=0.05,
        hysteresis_dwell_secs=30.0,
    )
    # Assert
    assert b.ramp_rate_per_sec == 0.10
    assert b.hysteresis_margin == 0.05
    assert b.hysteresis_dwell_secs == 30.0


def test_binding_distribute_without_envelope_guard_still_valid() -> None:
    # Arrange / Act — plain distribute, already-shipped shape, unaffected
    b = DistributeBinding(protocol="distribute", allocation_policy="equal_split")
    # Assert
    assert b.ramp_rate_per_sec is None
    assert b.hysteresis_margin is None
    assert b.hysteresis_dwell_secs is None


def test_binding_distribute_rejects_partial_envelope_guard() -> None:
    # Arrange / Act / Assert — all-or-nothing, not two-of-three
    with pytest.raises(ValidationError, match="all three or none"):
        DistributeBinding(
            protocol="distribute",
            allocation_policy="equal_split",
            ramp_rate_per_sec=0.10,
            hysteresis_margin=0.05,
        )
