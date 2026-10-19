"""Sizing preview flags: what the operator is told."""

import pytest

from src.shared.enums import (
    BessCoupling,
    ExportMode,
    GridPath,
    MarketRegion,
)
from src.shared.schemas.sizing import (
    SizingFlagCode,
    SizingGridInput,
)
from src.sizing.sizing_service import SizingService
from src.sizing.sizing_test_support import (
    _REGIONS,
    _request,
    _codes,
)


def test_near_distribution_limit_flag() -> None:
    service = SizingService(regions=_REGIONS)
    # 15 MW grid_peak needs ceil(15000kW/80kW)=188 containers * 56 gpus
    preview = service.preview(_request(target_gpu_count=56 * 188))
    assert SizingFlagCode.NEAR_DISTRIBUTION_LIMIT in _codes(preview)


def test_transmission_flag_only_when_path_known_non_off_grid() -> None:
    service = SizingService(regions=_REGIONS)
    grid = SizingGridInput(path=GridPath.FIRM, market_region=MarketRegion.ERCOT)
    preview = service.preview(_request(grid=grid, target_gpu_count=56 * 300))
    assert preview.limit_state.value == "over"
    assert SizingFlagCode.TRANSMISSION_MANUAL_ENGAGEMENT in _codes(preview)


def test_transmission_flag_absent_when_path_unknown() -> None:
    """path=None (not yet chosen) -> don't flag transmission engagement."""
    service = SizingService(regions=_REGIONS)
    preview = service.preview(_request(target_gpu_count=56 * 300))
    assert preview.limit_state.value == "over"
    assert SizingFlagCode.TRANSMISSION_MANUAL_ENGAGEMENT not in _codes(preview)


def test_flex_bess_shortfall_flag() -> None:
    service = SizingService(regions=_REGIONS)
    grid = SizingGridInput(path=GridPath.FLEXIBLE, market_region=MarketRegion.ERCOT)
    # tiny BESS relative to the flex requirement
    preview = service.preview(
        _request(
            grid=grid, bess_coupling=BessCoupling.AC_COUPLED, bess_capacity_mwh=0.01
        )
    )
    assert SizingFlagCode.FLEX_BESS_SHORTFALL in _codes(preview)


def test_reserve_shortfall_flag() -> None:
    service = SizingService(regions=_REGIONS)
    grid = SizingGridInput(path=GridPath.FIRM, market_region=MarketRegion.ERCOT)
    preview = service.preview(
        _request(
            grid=grid,
            ride_through_hours=10,
            bess_coupling=BessCoupling.AC_COUPLED,
            bess_capacity_mwh=0.01,
        )
    )
    assert SizingFlagCode.RESERVE_SHORTFALL in _codes(preview)


def test_export_review_flag_requires_explicit_export_mode() -> None:
    """export_mode unset -> no EXPORT_REVIEW (unknown != 'reviewing export')."""
    service = SizingService(regions=_REGIONS)
    preview = service.preview(_request())
    assert SizingFlagCode.EXPORT_REVIEW not in _codes(preview)


def test_export_review_flag_fires_when_export_mode_set() -> None:
    service = SizingService(regions=_REGIONS)
    grid = SizingGridInput(export_mode=ExportMode.LIMITED_EXPORT)
    preview = service.preview(_request(grid=grid))
    assert SizingFlagCode.EXPORT_REVIEW in _codes(preview)


def test_export_pcs_rating_unverified_ercot_export() -> None:
    service = SizingService(regions=_REGIONS)
    grid = SizingGridInput(
        market_region=MarketRegion.ERCOT, export_mode=ExportMode.EXPORT
    )
    preview = service.preview(_request(grid=grid))
    assert SizingFlagCode.EXPORT_PCS_RATING_UNVERIFIED in _codes(preview)


def test_islanding_flags() -> None:
    service = SizingService(regions=_REGIONS)
    grid = SizingGridInput(
        path=GridPath.FIRM, market_region=MarketRegion.ERCOT, intentional_islanding=True
    )
    preview = service.preview(_request(grid=grid))
    codes = _codes(preview)
    assert SizingFlagCode.ISLANDING_REVIEW_REQUIRED in codes
    assert SizingFlagCode.ISLANDING_TRANSFER_UNVERIFIED in codes


@pytest.mark.parametrize(
    ("coupling", "mwh", "expected"),
    [
        (BessCoupling.DC_EXTERNAL_PCS, 1.0, True),  # 3 racks = 1.14 MW < 2.32 MW
        (BessCoupling.DC_INTEGRATED_PCS, 1.0, True),  # same CATL racks
        (BessCoupling.DC_EXTERNAL_PCS, 10.0, False),  # 27 racks = 10.2 MW
        (BessCoupling.AC_COUPLED, 1.0, False),  # Megapack, not CATL racks
    ],
)
def test_bess_power_shortfall_when_catl_racks_cant_carry_the_job(
    coupling: BessCoupling, mwh: float, expected: bool
) -> None:
    # Arrange — 27 B200 containers riding through: battery carries 2.322 MW
    request = _request(
        target_gpu_count=27 * 56,
        bess_coupling=coupling,
        bess_capacity_mwh=mwh,
        ride_through_hours=2,
    )

    # Act
    actual = SizingService(regions=_REGIONS).preview(request)

    # Assert
    assert (SizingFlagCode.BESS_POWER_SHORTFALL in _codes(actual)) is expected
