"""ConfiguratorPayload validator unit tests."""

from typing import TypedDict
from uuid import UUID

import pytest
from pydantic import ValidationError

from src.shared.enums import (
    AwsPartition,
    BessCoupling,
    ClimateZone,
    DeploymentContext,
    EnergySource,
    GpuVariant,
    GridConnection,
    PrimaryWorkload,
)
from src.shared.schemas.configurator_payload import ConfiguratorPayload

DEPLOYMENT_ID: UUID = UUID("00000000-0000-0000-0000-000000000001")


class _PayloadKwargs(TypedDict):
    """Typed kwargs for ConfiguratorPayload construction in tests."""

    deployment_id: UUID
    operator_org: str
    deployment_site_name: str
    contact_email: str
    energy_source: EnergySource
    source_capacity_mw: float
    primary_workload: PrimaryWorkload
    gpu_variant: GpuVariant
    target_gpu_count: int
    bess_coupling: BessCoupling
    bess_capacity_mwh: float
    grid_connection: GridConnection
    climate_zone: ClimateZone
    deployment_context: DeploymentContext
    aws_partition: AwsPartition


def _kwargs(
    *,
    context: DeploymentContext = DeploymentContext.COMMERCIAL,
    coupling: BessCoupling = BessCoupling.AC_COUPLED,
    capacity_mwh: float = 5.0,
    partition: AwsPartition = AwsPartition.STANDARD,
) -> _PayloadKwargs:
    return _PayloadKwargs(
        deployment_id=DEPLOYMENT_ID,
        operator_org="acme",
        deployment_site_name="brookside dc-1",
        contact_email="ops@example.com",
        energy_source=EnergySource.GRID_HYBRID,
        source_capacity_mw=10.0,
        primary_workload=PrimaryWorkload.AI_TRAINING,
        gpu_variant=GpuVariant.H100_SXM,
        target_gpu_count=56,
        bess_coupling=coupling,
        bess_capacity_mwh=capacity_mwh,
        grid_connection=GridConnection.GRID_TIED,
        climate_zone=ClimateZone.TEMPERATE,
        deployment_context=context,
        aws_partition=partition,
    )


def test_rejects_bess_none_with_nonzero_capacity() -> None:
    """bess_coupling=NONE + capacity>0 -> ValidationError."""
    # Arrange
    kw = _kwargs(coupling=BessCoupling.NONE, capacity_mwh=5.0)

    # Act / Assert
    with pytest.raises(
        ValidationError, match="bess_coupling=NONE iff bess_capacity_mwh=0"
    ):
        ConfiguratorPayload(**kw)


def test_rejects_bess_coupled_with_zero_capacity() -> None:
    """bess_coupling=AC_COUPLED + capacity=0 -> ValidationError."""
    # Arrange
    kw = _kwargs(coupling=BessCoupling.AC_COUPLED, capacity_mwh=0.0)

    # Act / Assert
    with pytest.raises(
        ValidationError, match="bess_coupling=NONE iff bess_capacity_mwh=0"
    ):
        ConfiguratorPayload(**kw)


def test_rejects_standard_partition_for_federal() -> None:
    """aws_partition=standard + sovereign_government -> ValidationError."""
    # Arrange
    kw = _kwargs(
        context=DeploymentContext.SOVEREIGN_GOVERNMENT,
        partition=AwsPartition.STANDARD,
    )

    # Act / Assert
    with pytest.raises(
        ValidationError,
        match="aws_partition=standard only valid for deployment_context=commercial",
    ):
        ConfiguratorPayload(**kw)


def test_rejects_dod_dc_integrated_pcs() -> None:
    """defense_forward + dc_integrated_pcs -> ValidationError (CATL exclusion)."""
    # Arrange
    kw = _kwargs(
        context=DeploymentContext.DEFENSE_FORWARD,
        coupling=BessCoupling.DC_INTEGRATED_PCS,
        capacity_mwh=5.0,
        partition=AwsPartition.NONE,
    )

    # Act / Assert
    with pytest.raises(ValidationError, match="CATL exclusion"):
        ConfiguratorPayload(**kw)


def test_accepts_no_bess_with_zero_capacity() -> None:
    """Happy path for the no-BESS branch."""
    # Arrange
    kw = _kwargs(coupling=BessCoupling.NONE, capacity_mwh=0.0)

    # Act
    payload = ConfiguratorPayload(**kw)

    # Assert
    assert payload.bess_coupling == BessCoupling.NONE
