"""SizingService.preview() unit tests — flags + full composition."""

from src.shared.enums import (
    BessCoupling,
    DeploymentContext,
    ExportMode,
    FlexLevel,
    GpuVariant,
    GridPath,
    MarketRegion,
    OnsiteGenerationType,
)
from src.shared.schemas.configurator_grid import OnsiteGeneration
from src.shared.schemas.grid_regions import (
    FlexPreset,
    GridRegionsConfig,
    RegionDefaults,
)
from src.shared.schemas.sizing import (
    SizingFlagCode,
    SizingGridInput,
    SizingPreview,
    SizingPreviewRequest,
)
from src.sizing.sizing_service import SizingService

_REGIONS = GridRegionsConfig(
    defaults=RegionDefaults(distribution_limit_mw=20, distribution_near_mw=15),
    regions={},
    flex_levels={
        FlexLevel.STANDARD: FlexPreset(
            depth_pct=50,
            max_duration_h=4,
            max_events_yr=40,
            min_interval_h=20,
            notice_s=600,
        ),
    },
)
_NO_GEN = OnsiteGeneration(type=OnsiteGenerationType.NONE)


def _request(**overrides: object) -> SizingPreviewRequest:
    base: dict[str, object] = {
        "gpu_variant": GpuVariant.B200,
        "target_gpu_count": 56,
        "bess_coupling": BessCoupling.AC_COUPLED,
        "bess_capacity_mwh": 5.0,
        "deployment_context": DeploymentContext.COMMERCIAL,
        "onsite_generation": _NO_GEN,
        "grid": SizingGridInput(),
    }
    base.update(overrides)
    return SizingPreviewRequest.model_validate(base)


def _codes(preview: SizingPreview) -> set[SizingFlagCode]:
    return {f.code for f in preview.flags}


def test_preview_returns_site_peak_and_recommendation() -> None:
    # Arrange
    service = SizingService(regions=_REGIONS)
    # Act
    preview = service.preview(_request())
    # Assert — 1 container of B200 = 80 kW = 0.08 MW; off_grid since market_region unresolved
    assert preview.site_peak_mw == 0.08
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


def test_flex_no_bess_flag() -> None:
    service = SizingService(regions=_REGIONS)
    grid = SizingGridInput(path=GridPath.FLEXIBLE, market_region=MarketRegion.ERCOT)
    preview = service.preview(
        _request(grid=grid, bess_coupling=BessCoupling.NONE, bess_capacity_mwh=0)
    )
    assert SizingFlagCode.FLEX_NO_BESS in _codes(preview)
    assert SizingFlagCode.RECHARGE_HEADROOM in _codes(preview)


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


def test_bess_min_mwh_includes_reserve_and_flex() -> None:
    service = SizingService(regions=_REGIONS)
    grid = SizingGridInput(path=GridPath.FLEXIBLE, market_region=MarketRegion.ERCOT)
    preview = service.preview(
        _request(grid=grid, ride_through_hours=1, target_gpu_count=56 * 300)
    )
    assert preview.flex is not None
    assert preview.bess_min_mwh == preview.e_reserve_mwh + preview.flex.e_flex_mwh
