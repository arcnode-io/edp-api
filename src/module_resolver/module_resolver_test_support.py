"""Payload builder for module resolver tests; import explicitly."""

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
from src.shared.schemas.configurator_payload import ConfiguratorPayload

DEPLOYMENT_ID: UUID = UUID("00000000-0000-0000-0000-000000000001")


_OFF_GRID = Grid(path=GridPath.OFF_GRID)


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
