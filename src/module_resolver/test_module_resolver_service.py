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
    EnergySource,
    GpuVariant,
    GridConnection,
    PrimaryWorkload,
    SourcingTier,
)
from src.shared.schemas.configurator_payload import ConfiguratorPayload

DEPLOYMENT_ID: UUID = UUID("00000000-0000-0000-0000-000000000001")


def _payload(
    *,
    context: DeploymentContext = DeploymentContext.COMMERCIAL,
    coupling: BessCoupling = BessCoupling.AC_COUPLED,
    capacity_mwh: float = 5.0,
    gpu_count: int = 56,
    partition: AwsPartition = AwsPartition.STANDARD,
) -> ConfiguratorPayload:
    return ConfiguratorPayload(
        deployment_id=DEPLOYMENT_ID,
        operator_org="acme",
        deployment_site_name="brookside dc-1",
        contact_email="ops@example.com",
        energy_source=EnergySource.GRID_HYBRID,
        source_capacity_mw=10.0,
        primary_workload=PrimaryWorkload.AI_TRAINING,
        gpu_variant=GpuVariant.H100_SXM,
        target_gpu_count=gpu_count,
        bess_coupling=coupling,
        bess_capacity_mwh=capacity_mwh,
        grid_connection=GridConnection.GRID_TIED,
        climate_zone=ClimateZone.TEMPERATE,
        deployment_context=context,
        aws_partition=partition,
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
    (
        DeploymentContext.SOVEREIGN_GOVERNMENT,
        BessCoupling.NONE,
        AwsPartition.GOVCLOUD,
        DeploymentProfile.FEDERAL_NO_BESS,
    ),
    (
        DeploymentContext.SOVEREIGN_GOVERNMENT,
        BessCoupling.AC_COUPLED,
        AwsPartition.GOVCLOUD,
        DeploymentProfile.FEDERAL_AC,
    ),
    (
        DeploymentContext.SOVEREIGN_GOVERNMENT,
        BessCoupling.DC_EXTERNAL_PCS,
        AwsPartition.GOVCLOUD,
        DeploymentProfile.FEDERAL_DC_EXT,
    ),
    (
        DeploymentContext.SOVEREIGN_GOVERNMENT,
        BessCoupling.DC_INTEGRATED_PCS,
        AwsPartition.GOVCLOUD,
        DeploymentProfile.FEDERAL_DC_INT,
    ),
    (
        DeploymentContext.DEFENSE_FORWARD,
        BessCoupling.NONE,
        AwsPartition.NONE,
        DeploymentProfile.DOD_NO_BESS,
    ),
    (
        DeploymentContext.DEFENSE_FORWARD,
        BessCoupling.AC_COUPLED,
        AwsPartition.NONE,
        DeploymentProfile.DOD_AC,
    ),
    (
        DeploymentContext.DEFENSE_FORWARD,
        BessCoupling.DC_EXTERNAL_PCS,
        AwsPartition.NONE,
        DeploymentProfile.DOD_DC_EXT,
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
