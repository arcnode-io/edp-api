"""Payload kwargs builder for configurator payload tests; import explicitly."""

from typing import TypedDict
from uuid import UUID


from src.shared.enums import (
    AwsPartition,
    BessCoupling,
    ClimateZone,
    DeploymentContext,
    GpuVariant,
    GridPath,
    OnsiteGenerationType,
    PrimaryWorkload,
)
from src.shared.schemas.configurator_grid import (
    Grid,
    OnsiteGeneration,
    Site,
    SiteLocation,
)

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
    ride_through_hours: float
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
    ride_through_hours: float = 0.0,
    site: Site = _SITE,
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
        ride_through_hours=ride_through_hours,
        climate_zone=ClimateZone.TEMPERATE,
        deployment_context=context,
        aws_partition=partition,
        site=site,
        onsite_generation=_NO_GEN,
        grid=grid,
    )
