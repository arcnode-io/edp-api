"""measurement_ranges unit tests — ordering invariants for Bounds + Thresholds."""

import pytest
from pydantic import ValidationError

from src.shared.schemas.measurement_ranges import (
    Bounds,
    Thresholds,
    check_thresholds_inside_bounds,
)

# === Bounds ===


def test_bounds_happy_path() -> None:
    # Arrange / Act
    b = Bounds(min=0, max=100, nominal=50)
    # Assert
    assert b.min == 0.0
    assert b.max == 100.0
    assert b.nominal == 50.0


def test_bounds_rejects_min_equal_max() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match=r"min.*must be < max"):
        Bounds(min=100, max=100, nominal=100)


def test_bounds_rejects_nominal_outside_range() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match=r"nominal.*must lie within"):
        Bounds(min=0, max=100, nominal=150)


# === Thresholds ===


def test_thresholds_happy_path() -> None:
    # Arrange / Act
    t = Thresholds(warn_min=15, warn_max=90, alarm_min=5, alarm_max=95)
    # Assert
    assert t.alarm_min == 5.0
    assert t.alarm_max == 95.0


def test_thresholds_rejects_warn_outside_alarm() -> None:
    # Arrange — warn_min < alarm_min (warn band must nest inside alarm band)
    # Act / Assert
    with pytest.raises(ValidationError, match=r"thresholds must satisfy"):
        Thresholds(warn_min=0, warn_max=90, alarm_min=5, alarm_max=95)


def test_thresholds_rejects_warn_min_greater_than_warn_max() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match=r"thresholds must satisfy"):
        Thresholds(warn_min=50, warn_max=10, alarm_min=5, alarm_max=95)


# === check_thresholds_inside_bounds ===


def test_check_passes_when_thresholds_inside_bounds() -> None:
    # Arrange
    bounds = Bounds(min=0, max=100, nominal=50)
    thresholds = Thresholds(warn_min=15, warn_max=90, alarm_min=5, alarm_max=95)
    # Act / Assert — no raise
    check_thresholds_inside_bounds(bounds, thresholds)


def test_check_raises_when_alarm_max_exceeds_bounds_max() -> None:
    # Arrange — alarm_max=110 but device cannot report >100
    bounds = Bounds(min=0, max=100, nominal=50)
    thresholds = Thresholds(warn_min=15, warn_max=90, alarm_min=5, alarm_max=110)
    # Act / Assert
    with pytest.raises(ValueError, match=r"alarm_max.*alarm unreachable"):
        check_thresholds_inside_bounds(bounds, thresholds)


def test_check_raises_when_alarm_min_below_bounds_min() -> None:
    # Arrange — alarm_min=-10 but device cannot report <0
    bounds = Bounds(min=0, max=100, nominal=50)
    thresholds = Thresholds(warn_min=15, warn_max=90, alarm_min=-10, alarm_max=95)
    # Act / Assert
    with pytest.raises(ValueError, match=r"alarm_min.*alarm unreachable"):
        check_thresholds_inside_bounds(bounds, thresholds)


def test_check_noop_when_either_none() -> None:
    # Arrange / Act / Assert — either side None = nothing to check
    check_thresholds_inside_bounds(None, None)
    check_thresholds_inside_bounds(Bounds(min=0, max=10, nominal=5), None)
    check_thresholds_inside_bounds(
        None, Thresholds(warn_min=1, warn_max=9, alarm_min=0, alarm_max=10)
    )
