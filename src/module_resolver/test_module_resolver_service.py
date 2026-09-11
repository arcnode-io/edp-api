"""ModuleResolverService unit tests. AAA pattern, table-driven over the 11 profiles."""

from uuid import UUID

import pytest

from src.module_resolver.module_resolver_service import ModuleResolverService
from src.shared.enums import (
    AwsPartition,
    BessCoupling,
    ClimateZone,
    DeploymentContext,
    DeploymentProfile,
    EmsTarget,
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
    SourcingTier,
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

DEPLOYMENT_ID: UUID = UUID("00000000-0000-0000-0000-000000000001")

_OFF_GRID = Grid(path=GridPath.OFF_GRID)
_FLEXIBLE_GRID = Grid(
    path=GridPath.FLEXIBLE,
    service_type=ServiceType.FLEXIBLE,
    flex_obligation=FlexObligation(
        level=FlexLevel.STANDARD,
        depth_pct=50,
        max_duration_h=4,
        max_events_yr=40,
        min_interval_h=20,
        notice_s=600,
    ),
    wires_owner=WiresOwner(id="oncor", name="Oncor", type=WiresOwnerType.TDSP),
    market_region=MarketRegion.ERCOT,
)
_GRID_REVENUE_FIRM_GRID = Grid(
    path=GridPath.GRID_REVENUE,
    service_type=ServiceType.FIRM,
    export_mode=ExportMode.LIMITED_EXPORT,
    export_limit_mw=5.0,
    market_access=MarketAccess.AGGREGATED,
    market_program=MarketProgram.ERCOT_DGR,
    settlement_point="HB_NORTH",
    wires_owner=WiresOwner(id="oncor", name="Oncor", type=WiresOwnerType.TDSP),
    market_region=MarketRegion.ERCOT,
)


def _payload(
    *,
    context: DeploymentContext = DeploymentContext.COMMERCIAL,
    coupling: BessCoupling = BessCoupling.AC_COUPLED,
    capacity_mwh: float = 5.0,
    gpu_count: int = 56,
    partition: AwsPartition = AwsPartition.STANDARD,
    grid: Grid = _OFF_GRID,
) -> ConfiguratorPayload:
    return ConfiguratorPayload(
        deployment_id=DEPLOYMENT_ID,
        operator_org="acme",
        deployment_site_name="brookside dc-1",
        contact_email="ops@example.com",
        primary_workload=PrimaryWorkload.AI_TRAINING,
        gpu_variant=GpuVariant.H100_SXM,
        target_gpu_count=gpu_count,
        bess_coupling=coupling,
        bess_capacity_mwh=capacity_mwh,
        climate_zone=ClimateZone.TEMPERATE,
        deployment_context=context,
        aws_partition=partition,
        site=Site(location=SiteLocation(lat=32.7, lon=-96.8), country="US"),
        onsite_generation=OnsiteGeneration(type=OnsiteGenerationType.NONE),
        grid=grid,
    )


def test_resolves_commercial_ac_profile() -> None:
    """Happy path: commercial + ac_coupled -> COMMERCIAL_AC."""
    # Arrange
    service = ModuleResolverService()
    payload = _payload()

    # Act
    actual = service.resolve(payload)

    # Assert
    assert actual.deployment_profile == DeploymentProfile.COMMERCIAL_AC


# 11 valid combos -> 11 profiles. Drives the matrix exhaustively.
_PROFILE_CASES: list[
    tuple[DeploymentContext, BessCoupling, AwsPartition, DeploymentProfile]
] = [
    (
        DeploymentContext.COMMERCIAL,
        BessCoupling.NONE,
        AwsPartition.STANDARD,
        DeploymentProfile.COMMERCIAL_NO_BESS,
    ),
    (
        DeploymentContext.COMMERCIAL,
        BessCoupling.AC_COUPLED,
        AwsPartition.STANDARD,
        DeploymentProfile.COMMERCIAL_AC,
    ),
    (
        DeploymentContext.COMMERCIAL,
        BessCoupling.DC_EXTERNAL_PCS,
        AwsPartition.STANDARD,
        DeploymentProfile.COMMERCIAL_DC_EXT,
    ),
    (
        DeploymentContext.COMMERCIAL,
        BessCoupling.DC_INTEGRATED_PCS,
        AwsPartition.STANDARD,
        DeploymentProfile.COMMERCIAL_DC_INT,
    ),
    # Sovereign government — same hardware as defense_forward; SourcingTier
    # distinguishes procurement path (federal_civilian vs dod_eligible).
    (
        DeploymentContext.SOVEREIGN_GOVERNMENT,
        BessCoupling.NONE,
        AwsPartition.GOVCLOUD,
        DeploymentProfile.DEFENSE_NO_BESS,
    ),
    (
        DeploymentContext.SOVEREIGN_GOVERNMENT,
        BessCoupling.AC_COUPLED,
        AwsPartition.GOVCLOUD,
        DeploymentProfile.DEFENSE_AC,
    ),
    (
        DeploymentContext.SOVEREIGN_GOVERNMENT,
        BessCoupling.DC_EXTERNAL_PCS,
        AwsPartition.GOVCLOUD,
        DeploymentProfile.DEFENSE_DC_EXT,
    ),
    # (SOVEREIGN_GOVERNMENT, DC_INTEGRATED_PCS) intentionally absent —
    # rejected at ConfiguratorPayload validator (CATL exclusion).
    (
        DeploymentContext.DEFENSE_FORWARD,
        BessCoupling.NONE,
        AwsPartition.NONE,
        DeploymentProfile.DEFENSE_NO_BESS,
    ),
    (
        DeploymentContext.DEFENSE_FORWARD,
        BessCoupling.AC_COUPLED,
        AwsPartition.NONE,
        DeploymentProfile.DEFENSE_AC,
    ),
    (
        DeploymentContext.DEFENSE_FORWARD,
        BessCoupling.DC_EXTERNAL_PCS,
        AwsPartition.NONE,
        DeploymentProfile.DEFENSE_DC_EXT,
    ),
]


@pytest.mark.parametrize(
    ("context", "coupling", "partition", "expected"), _PROFILE_CASES
)
def test_resolves_full_profile_matrix(
    context: DeploymentContext,
    coupling: BessCoupling,
    partition: AwsPartition,
    expected: DeploymentProfile,
) -> None:
    """All 11 (context, coupling) combos resolve to the expected profile."""
    # Arrange
    service = ModuleResolverService()
    capacity = 0.0 if coupling == BessCoupling.NONE else 5.0
    payload = _payload(
        context=context, coupling=coupling, capacity_mwh=capacity, partition=partition
    )

    # Act
    actual = service.resolve(payload)

    # Assert
    assert actual.deployment_profile == expected


def test_rounds_up_to_full_compute_container() -> None:
    """target_gpu_count=100 -> 2 containers of 56 (gpu_count=112)."""
    # Arrange
    service = ModuleResolverService()
    payload = _payload(gpu_count=100)

    # Act
    actual = service.resolve(payload)

    # Assert
    assert actual.compute_container_count == 2
    assert actual.gpu_count == 112


def test_grid_container_absent_when_no_bess() -> None:
    """bess_coupling=NONE -> grid_container_present=False."""
    # Arrange
    service = ModuleResolverService()
    payload = _payload(coupling=BessCoupling.NONE, capacity_mwh=0.0)

    # Act
    actual = service.resolve(payload)

    # Assert
    assert actual.grid_container_present is False


def test_der_enabled_false_for_off_grid() -> None:
    """path=off_grid -> service_type/market_access both at default -> der_enabled=False."""
    # Arrange
    service = ModuleResolverService()
    payload = _payload(grid=_OFF_GRID)

    # Act
    actual = service.resolve(payload)

    # Assert
    assert actual.der_enabled is False


def test_der_enabled_true_for_flexible_service_type() -> None:
    """D5: service_type=flexible -> der_enabled=True, independent of market_access."""
    # Arrange
    service = ModuleResolverService()
    payload = _payload(grid=_FLEXIBLE_GRID)

    # Act
    actual = service.resolve(payload)

    # Assert
    assert actual.der_enabled is True


def test_der_enabled_true_for_market_access() -> None:
    """D5: market_access != none -> der_enabled=True, even with service_type=firm."""
    # Arrange
    service = ModuleResolverService()
    payload = _payload(grid=_GRID_REVENUE_FIRM_GRID)

    # Act
    actual = service.resolve(payload)

    # Assert
    assert actual.der_enabled is True


def test_derives_sourcing_tier_and_ems_target() -> None:
    """sovereign_government + govcloud -> federal_civilian + aws_govcloud."""
    # Arrange
    service = ModuleResolverService()
    payload = _payload(
        context=DeploymentContext.SOVEREIGN_GOVERNMENT,
        partition=AwsPartition.GOVCLOUD,
    )

    # Act
    actual = service.resolve(payload)

    # Assert
    assert actual.sourcing_tier == SourcingTier.FEDERAL_CIVILIAN
    assert actual.ems_target == EmsTarget.AWS_GOVCLOUD
