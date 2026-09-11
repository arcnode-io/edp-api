"""validate_against_regions unit tests — V4b, V6, SP, FL (region-dependent rules)."""

from uuid import UUID

import pytest

from src.grid.region_validation import validate_against_regions
from src.shared.enums import (
    AwsPartition,
    BessCoupling,
    ClimateZone,
    DeploymentContext,
    ExportMode,
    FlexLevel,
    GpuVariant,
    GridPath,
    MarketAccess,
    MarketProgram,
    MarketRegion,
    OnsiteGenerationType,
    PrimaryWorkload,
    ServiceType,
    WiresOwnerType,
)
from src.shared.schemas.configurator_grid import (
    FlexObligation,
    Grid,
    OnsiteGeneration,
    Site,
    SiteLocation,
    WiresOwner,
)
from src.shared.schemas.configurator_payload import ConfiguratorPayload
from src.shared.schemas.grid_regions import (
    FlexPreset,
    GridRegionsConfig,
    RegionConfig,
    RegionDefaults,
)

_REGIONS = GridRegionsConfig(
    defaults=RegionDefaults(distribution_limit_mw=20, distribution_near_mw=15),
    regions={
        MarketRegion.ERCOT: RegionConfig(
            large_load_mw=75,
            dg_export_max_mw=10,
            dg_registration_mw=1,
            market_programs=[MarketProgram.ERCOT_ADER, MarketProgram.ERCOT_DGR],
            settlement_points=["HB_NORTH"],
        ),
        MarketRegion.CAISO: RegionConfig(
            large_load_mw=None,
            dg_export_max_mw=None,
            dg_registration_mw=None,
            market_programs=[],
            settlement_points=[],
        ),
    },
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

_WIRES_OWNER = WiresOwner(id="oncor", name="Oncor", type=WiresOwnerType.TDSP)
_SITE = Site(location=SiteLocation(lat=32.7, lon=-96.8), country="US")
_NO_GEN = OnsiteGeneration(type=OnsiteGenerationType.NONE)


def _flex(**overrides: object) -> FlexObligation:
    base: dict[str, object] = {
        "level": FlexLevel.STANDARD,
        "depth_pct": 50,
        "max_duration_h": 4,
        "max_events_yr": 40,
        "min_interval_h": 20,
        "notice_s": 600,
    }
    base.update(overrides)
    return FlexObligation.model_validate(base)


def _payload(grid: Grid) -> ConfiguratorPayload:
    return ConfiguratorPayload(
        deployment_id=UUID("00000000-0000-0000-0000-000000000001"),
        operator_org="acme",
        deployment_site_name="brookside dc-1",
        contact_email="ops@example.com",
        primary_workload=PrimaryWorkload.AI_TRAINING,
        gpu_variant=GpuVariant.H100_SXM,
        target_gpu_count=56,
        bess_coupling=BessCoupling.AC_COUPLED,
        bess_capacity_mwh=5.0,
        climate_zone=ClimateZone.TEMPERATE,
        deployment_context=DeploymentContext.COMMERCIAL,
        aws_partition=AwsPartition.STANDARD,
        site=_SITE,
        onsite_generation=_NO_GEN,
        grid=grid,
    )


def _grid_revenue(**overrides: object) -> Grid:
    base: dict[str, object] = {
        "path": GridPath.GRID_REVENUE,
        "service_type": ServiceType.FLEXIBLE,
        "flex_obligation": _flex(),
        "export_mode": ExportMode.LIMITED_EXPORT,
        "export_limit_mw": 5.0,
        "market_access": MarketAccess.DIRECT,
        "market_program": MarketProgram.ERCOT_ADER,
        "settlement_point": "HB_NORTH",
        "wires_owner": _WIRES_OWNER,
        "market_region": MarketRegion.ERCOT,
    }
    base.update(overrides)
    return Grid.model_validate(base)


def test_happy_path_grid_revenue_passes() -> None:
    # Arrange
    payload = _payload(_grid_revenue())
    # Act / Assert — no raise
    validate_against_regions(payload, _REGIONS)


# --- V4b: market_program must be offered in the region ---


def test_v4b_rejects_program_not_offered_in_region() -> None:
    # Arrange — CAISO offers no market programs at all
    grid = _grid_revenue(
        market_region=MarketRegion.CAISO,
        wires_owner=WiresOwner(id="pge", name="PG&E", type=WiresOwnerType.IOU),
    )
    payload = _payload(grid)
    # Act / Assert
    with pytest.raises(ValueError, match="not offered"):
        validate_against_regions(payload, _REGIONS)


# --- V6: ERCOT limited-export can't exceed the DG cap ---


def test_v6_rejects_export_limit_above_dg_cap() -> None:
    # Arrange — dg_export_max_mw is 10 for ERCOT
    payload = _payload(_grid_revenue(export_limit_mw=15.0))
    # Act / Assert
    with pytest.raises(ValueError, match="exceeds ERCOT dg_export_max_mw"):
        validate_against_regions(payload, _REGIONS)


def test_v6_accepts_export_limit_at_cap() -> None:
    # Arrange
    payload = _payload(_grid_revenue(export_limit_mw=10.0))
    # Act / Assert — no raise
    validate_against_regions(payload, _REGIONS)


# --- SP: settlement_point only valid for ERCOT, must be a known point ---


def test_sp_rejects_unknown_settlement_point() -> None:
    # Arrange
    payload = _payload(_grid_revenue(settlement_point="HB_HOUSTON"))
    # Act / Assert
    with pytest.raises(ValueError, match="not in"):
        validate_against_regions(payload, _REGIONS)


# --- FL: non-custom flex level numbers must match the yaml preset (D12) ---


def test_fl_rejects_drifted_preset_numbers() -> None:
    # Arrange — depth_pct doesn't match the standard preset (50)
    grid = _grid_revenue(flex_obligation=_flex(depth_pct=99))
    payload = _payload(grid)
    # Act / Assert
    with pytest.raises(ValueError, match="must match preset"):
        validate_against_regions(payload, _REGIONS)


def test_fl_allows_custom_level_with_any_numbers() -> None:
    # Arrange — custom level is exempt from preset matching
    grid = _grid_revenue(
        flex_obligation=_flex(level=FlexLevel.CUSTOM, depth_pct=99, notice_s=1)
    )
    payload = _payload(grid)
    # Act / Assert — no raise
    validate_against_regions(payload, _REGIONS)
