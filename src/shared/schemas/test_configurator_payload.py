"""ConfiguratorPayload validator unit tests (top-level rules only — grid rules in
test_configurator_grid.py)."""

from typing import TypedDict
from uuid import UUID

import pytest
from pydantic import ValidationError

from src.shared.enums import (
    AwsPartition,
    BessCoupling,
    ClimateZone,
    DeploymentContext,
    GpuVariant,
    GridPath,
    MarketRegion,
    OnsiteGenerationType,
    PrimaryWorkload,
    ServiceType,
    WiresOwnerType,
)
from src.shared.schemas.configurator_grid import (
    Grid,
    OnsiteGeneration,
    Site,
    SiteLocation,
    WiresOwner,
)
from src.shared.schemas.configurator_payload import ConfiguratorPayload

DEPLOYMENT_ID: UUID = UUID("00000000-0000-0000-0000-000000000001")

_SITE = Site(location=SiteLocation(lat=32.7, lon=-96.8), country="US", state="TX")
_NO_GEN = OnsiteGeneration(type=OnsiteGenerationType.NONE, capacity_mw=None)
_OFF_GRID = Grid(path=GridPath.OFF_GRID)


class _PayloadKwargs(TypedDict):
    """Typed kwargs for ConfiguratorPayload construction in tests."""

    deployment_id: UUID
    operator_org: str
    deployment_site_name: str
    contact_email: str
    primary_workload: PrimaryWorkload
    gpu_variant: GpuVariant
    target_gpu_count: int
    bess_coupling: BessCoupling
    bess_capacity_mwh: float
    climate_zone: ClimateZone
    deployment_context: DeploymentContext
    aws_partition: AwsPartition
    site: Site
    onsite_generation: OnsiteGeneration
    grid: Grid


def _kwargs(
    *,
    context: DeploymentContext = DeploymentContext.COMMERCIAL,
    coupling: BessCoupling = BessCoupling.AC_COUPLED,
    capacity_mwh: float = 5.0,
    partition: AwsPartition = AwsPartition.STANDARD,
    grid: Grid = _OFF_GRID,
) -> _PayloadKwargs:
    return _PayloadKwargs(
        deployment_id=DEPLOYMENT_ID,
        operator_org="acme",
        deployment_site_name="brookside dc-1",
        contact_email="ops@example.com",
        primary_workload=PrimaryWorkload.AI_TRAINING,
        gpu_variant=GpuVariant.H100_SXM,
        target_gpu_count=56,
        bess_coupling=coupling,
        bess_capacity_mwh=capacity_mwh,
        climate_zone=ClimateZone.TEMPERATE,
        deployment_context=context,
        aws_partition=partition,
        site=_SITE,
        onsite_generation=_NO_GEN,
        grid=grid,
    )


def test_rejects_bess_none_with_nonzero_capacity() -> None:
    # Arrange
    kw = _kwargs(coupling=BessCoupling.NONE, capacity_mwh=5.0)

    # Act / Assert
    with pytest.raises(
        ValidationError, match="bess_coupling=NONE iff bess_capacity_mwh=0"
    ):
        ConfiguratorPayload(**kw)


def test_rejects_bess_coupled_with_zero_capacity() -> None:
    # Arrange
    kw = _kwargs(coupling=BessCoupling.AC_COUPLED, capacity_mwh=0.0)

    # Act / Assert
    with pytest.raises(
        ValidationError, match="bess_coupling=NONE iff bess_capacity_mwh=0"
    ):
        ConfiguratorPayload(**kw)


def test_rejects_standard_partition_for_federal() -> None:
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


def test_rejects_defense_forward_dc_integrated_pcs() -> None:
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


def test_rejects_sovereign_government_dc_integrated_pcs() -> None:
    """Both federal contexts resolve to the same DEFENSE_* hardware variants."""
    # Arrange
    kw = _kwargs(
        context=DeploymentContext.SOVEREIGN_GOVERNMENT,
        coupling=BessCoupling.DC_INTEGRATED_PCS,
        capacity_mwh=5.0,
        partition=AwsPartition.GOVCLOUD,
    )

    # Act / Assert
    with pytest.raises(ValidationError, match="CATL exclusion"):
        ConfiguratorPayload(**kw)


def test_accepts_no_bess_with_zero_capacity() -> None:
    """Happy path for the no-BESS, off-grid branch."""
    # Arrange
    kw = _kwargs(coupling=BessCoupling.NONE, capacity_mwh=0.0)

    # Act
    payload = ConfiguratorPayload(**kw)

    # Assert
    assert payload.bess_coupling == BessCoupling.NONE
    assert payload.grid.path == GridPath.OFF_GRID


def test_islanding_requires_bess() -> None:
    """V9: intentional_islanding=true + bess_coupling=none -> ValidationError."""
    # Arrange — firm path (off_grid forces islanding false, so this needs grid-tied)
    grid = Grid(
        path=GridPath.FIRM,
        service_type=ServiceType.FIRM,
        wires_owner=WiresOwner(id="oncor", name="Oncor", type=WiresOwnerType.TDSP),
        market_region=MarketRegion.ERCOT,
        intentional_islanding=True,
    )
    kw = _kwargs(coupling=BessCoupling.NONE, capacity_mwh=0.0, grid=grid)

    # Act / Assert
    with pytest.raises(ValidationError, match="intentional_islanding=true requires"):
        ConfiguratorPayload(**kw)


def test_islanding_with_bess_is_valid() -> None:
    """V9 happy path: intentional_islanding=true is fine with a real BESS."""
    # Arrange
    grid = Grid(
        path=GridPath.FIRM,
        service_type=ServiceType.FIRM,
        wires_owner=WiresOwner(id="oncor", name="Oncor", type=WiresOwnerType.TDSP),
        market_region=MarketRegion.ERCOT,
        intentional_islanding=True,
    )
    kw = _kwargs(coupling=BessCoupling.AC_COUPLED, capacity_mwh=5.0, grid=grid)

    # Act
    payload = ConfiguratorPayload(**kw)

    # Assert
    assert payload.grid.intentional_islanding is True
