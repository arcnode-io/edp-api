"""dc_ext PCS count follows the battery's power job, not the grid containers."""

from typing import Final

import pytest

from src.shared.enums import ExportMode, FlexLevel, GridPath, ServiceType
from src.shared.schemas.configurator_grid import FlexObligation
from src.shared.schemas.sizing import SizingGridInput
from src.sizing.pcs_sizing import bess_dc_power_mw, bess_power_need_mw, pcs_count

# 27 B200 compute containers x 86 kW (80 kW + 6 kW dry cooler) = 3 grid containers
GRID_PEAK_MW: Final[float] = 2.322

STANDARD: Final[FlexObligation] = FlexObligation(
    level=FlexLevel.STANDARD,
    depth_pct=50,
    max_duration_h=4,
    max_events_yr=40,
    min_interval_h=20,
    notice_s=600,
)


def test_ride_through_carries_the_whole_site() -> None:
    # Arrange
    grid = SizingGridInput(path=GridPath.FIRM, service_type=ServiceType.FIRM)

    # Act
    actual = bess_power_need_mw(
        grid_peak_mw=GRID_PEAK_MW,
        ride_through_hours=2,
        grid=grid,
        flex=None,
        bess_capacity_mwh=10,
    )

    # Assert
    assert actual == GRID_PEAK_MW


def test_off_grid_carries_the_whole_site() -> None:
    # Arrange
    grid = SizingGridInput(path=GridPath.OFF_GRID)

    # Act
    actual = bess_power_need_mw(
        grid_peak_mw=GRID_PEAK_MW,
        ride_through_hours=0,
        grid=grid,
        flex=None,
        bess_capacity_mwh=10,
    )

    # Assert
    assert actual == GRID_PEAK_MW


def test_flex_only_covers_the_curtailed_depth() -> None:
    # Arrange — 50% of 2.322 MW = 1.161 MW beats the 0.257 MW recharge
    grid = SizingGridInput(path=GridPath.FLEXIBLE, flex_obligation=STANDARD)

    # Act
    actual = bess_power_need_mw(
        grid_peak_mw=GRID_PEAK_MW,
        ride_through_hours=0,
        grid=grid,
        flex=STANDARD,
        bess_capacity_mwh=10,
    )

    # Assert
    assert actual == pytest.approx(1.161)


def test_limited_export_covers_the_export_limit() -> None:
    # Arrange
    grid = SizingGridInput(
        path=GridPath.GRID_REVENUE,
        service_type=ServiceType.FIRM,
        export_mode=ExportMode.LIMITED_EXPORT,
        export_limit_mw=3.0,
    )

    # Act
    actual = bess_power_need_mw(
        grid_peak_mw=GRID_PEAK_MW,
        ride_through_hours=0,
        grid=grid,
        flex=None,
        bess_capacity_mwh=10,
    )

    # Assert
    assert actual == 3.0


def test_unlimited_export_covers_the_battery_itself() -> None:
    # Arrange — 4 MWh = 11 CATL racks at 379.4 kW
    grid = SizingGridInput(
        path=GridPath.GRID_REVENUE,
        service_type=ServiceType.FIRM,
        export_mode=ExportMode.EXPORT,
    )

    # Act
    actual = bess_power_need_mw(
        grid_peak_mw=GRID_PEAK_MW,
        ride_through_hours=0,
        grid=grid,
        flex=None,
        bess_capacity_mwh=4,
    )

    # Assert
    assert actual == pytest.approx(4.1734)


def test_firm_with_no_power_job_needs_nothing() -> None:
    # Arrange
    grid = SizingGridInput(path=GridPath.FIRM, service_type=ServiceType.FIRM)

    # Act
    actual = bess_power_need_mw(
        grid_peak_mw=GRID_PEAK_MW,
        ride_through_hours=0,
        grid=grid,
        flex=None,
        bess_capacity_mwh=10,
    )

    # Assert
    assert actual == 0.0


@pytest.mark.parametrize(
    ("p_need_mw", "expected"),
    [(0.0, 1), (1.043, 1), (1.161, 2), (7.74, 8)],
)
def test_pcs_count_is_ceil_of_need_over_1043_kw_with_a_floor_of_one(
    p_need_mw: float, expected: int
) -> None:
    # Act
    actual = pcs_count(p_need_mw)

    # Assert
    assert actual == expected


def test_one_mwh_of_catl_is_three_racks_of_dc_power() -> None:
    # Act
    actual = bess_dc_power_mw(1.0)

    # Assert
    assert actual == pytest.approx(1.1382)
