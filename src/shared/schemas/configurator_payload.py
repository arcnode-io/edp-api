"""Customer-submitted configuration. Forwarded verbatim from platform-api."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from src.shared.enums import (
    AwsPartition,
    BessCoupling,
    ClimateZone,
    DeploymentContext,
    GpuVariant,
    GridPath,
    PrimaryWorkload,
)
from src.shared.schemas.configurator_grid import Grid, OnsiteGeneration, Site


class ConfiguratorPayload(BaseModel):
    """Single source of truth for a deployment's user-supplied configuration."""

    model_config = ConfigDict(extra="forbid")

    deployment_id: UUID

    operator_org: str
    deployment_site_name: str
    contact_email: EmailStr

    primary_workload: PrimaryWorkload
    gpu_variant: GpuVariant
    target_gpu_count: int = Field(ge=1)

    bess_coupling: BessCoupling
    bess_capacity_mwh: float = Field(gt=0)  # every site has a BESS
    ride_through_hours: float = Field(ge=0, default=0)
    # May the EMS cap GPU power on its own to hold the operating envelope?
    compute_shed_enabled: bool = False

    climate_zone: ClimateZone
    deployment_context: DeploymentContext
    aws_partition: AwsPartition

    site: Site
    onsite_generation: OnsiteGeneration
    grid: Grid

    @model_validator(mode="after")
    def standard_partition_commercial_only(self) -> "ConfiguratorPayload":
        """Reject standard AWS partition for federal/defense deployments."""
        # Reason: federal/defense workloads cannot run in commercial AWS regions.
        if (
            self.aws_partition == AwsPartition.STANDARD
            and self.deployment_context != DeploymentContext.COMMERCIAL
        ):
            raise ValueError(
                "aws_partition=standard only valid for deployment_context=commercial"
            )
        return self

    @model_validator(mode="after")
    def federal_excludes_dc_coupling(self) -> "ConfiguratorPayload":
        """Reject sovereign_government / defense_forward + either DC coupling.

        Reason: the only DC battery we spec is CATL EnerOne+ (with or without
        CATL's PCS), and CATL is on DOD 1260H. Federal sites go AC (Megapack).
        """
        federal_contexts = {
            DeploymentContext.SOVEREIGN_GOVERNMENT,
            DeploymentContext.DEFENSE_FORWARD,
        }
        dc_couplings = {BessCoupling.DC_INTEGRATED_PCS, BessCoupling.DC_EXTERNAL_PCS}
        if (
            self.deployment_context in federal_contexts
            and self.bess_coupling in dc_couplings
        ):
            raise ValueError(
                f"{self.deployment_context.value} + {self.bess_coupling.value} "
                "is not procurable (CATL exclusion)"
            )
        return self

    @model_validator(mode="after")
    def islanding_requires_ride_through_hours(self) -> "ConfiguratorPayload":
        """V10: intentional islanding requires a positive ride-through reserve."""
        if self.grid.intentional_islanding and self.ride_through_hours <= 0:
            raise ValueError(
                "grid.intentional_islanding=true requires ride_through_hours > 0"
            )
        return self

    @model_validator(mode="after")
    def grid_connected_requires_coordinates(self) -> "ConfiguratorPayload":
        """Grid-connected paths need lat/lon to resolve the wires owner."""
        loc = self.site.location
        if self.grid.path != GridPath.OFF_GRID and (loc.lat is None or loc.lon is None):
            raise ValueError(
                f"grid.path={self.grid.path.value} requires site.location lat and lon"
            )
        return self
