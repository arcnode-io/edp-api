"""SizingService.preview() unit tests — flags + full composition."""

import pytest

from src.shared.enums import (
    GridPath,
    MarketRegion,
)
from src.shared.schemas.sizing import (
    SizingGridInput,
)
from src.sizing.sizing_service import SizingService
from src.sizing.sizing_test_support import (
    _REGIONS,
    _request,
)


def test_preview_returns_site_peak_and_recommendation() -> None:
    # Arrange
    service = SizingService(regions=_REGIONS)
    # Act
    preview = service.preview(_request())
    # Assert — 1 container of B200 = 80 kW + 6 kW fans = 0.086 MW; off_grid since
    # market_region unresolved
    assert preview.site_peak_mw == pytest.approx(0.086)
    assert preview.recommended_path == GridPath.OFF_GRID


def test_preview_flexible_path_includes_flex_block() -> None:
    # Arrange
    service = SizingService(regions=_REGIONS)
    grid = SizingGridInput(path=GridPath.FLEXIBLE, market_region=MarketRegion.ERCOT)
    # Act
    preview = service.preview(_request(grid=grid, target_gpu_count=56 * 300))

    # Assert — big enough site to clear distribution limit and exercise flex math
    assert preview.flex is not None
    assert preview.flex.e_flex_mwh > 0


def test_preview_firm_path_has_no_flex_block() -> None:
    service = SizingService(regions=_REGIONS)
    grid = SizingGridInput(path=GridPath.FIRM, market_region=MarketRegion.ERCOT)
    preview = service.preview(_request(grid=grid))
    assert preview.flex is None


def test_bess_min_mwh_includes_reserve_and_flex() -> None:
    service = SizingService(regions=_REGIONS)
    grid = SizingGridInput(path=GridPath.FLEXIBLE, market_region=MarketRegion.ERCOT)
    preview = service.preview(
        _request(grid=grid, ride_through_hours=1, target_gpu_count=56 * 300)
    )
    assert preview.flex is not None
    assert preview.bess_min_mwh == preview.e_reserve_mwh + preview.flex.e_flex_mwh
