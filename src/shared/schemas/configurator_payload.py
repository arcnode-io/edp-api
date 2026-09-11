"""Customer-submitted configuration. Forwarded verbatim from platform-api."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from src.shared.enums import (
    AwsPartition,
    BessCoupling,
    ClimateZone,
    DeploymentContext,
    GpuVariant,
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
    bess_capacity_mwh: float = Field(ge=0)
    ride_through_hours: float = Field(ge=0, default=0)

    climate_zone: ClimateZone
    deployment_context: DeploymentContext
    aws_partition: AwsPartition

    site: Site
    onsite_generation: OnsiteGeneration
    grid: Grid

    @model_validator(mode="after")
    def bess_consistency(self) -> "ConfiguratorPayload":
        """Reject NONE-coupling-with-capacity and coupled-with-zero-capacity."""
        # Reason: NONE coupling iff zero capacity. Catch contradictions at ingress.
        if (self.bess_coupling == BessCoupling.NONE) != (self.bess_capacity_mwh == 0):
            raise ValueError("bess_coupling=NONE iff bess_capacity_mwh=0")
        return self

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
    def federal_excludes_dc_integrated_pcs(self) -> "ConfiguratorPayload":
        """Reject sovereign_government / defense_forward + dc_integrated_pcs.

        Reason: integrated DC PCS is CATL-only; CATL excluded from federal-
        civilian + DoD procurement. Both deployment contexts resolve to the
        same hardware variants (DEFENSE_*) so the constraint applies uniformly.
        """
        federal_contexts = {
            DeploymentContext.SOVEREIGN_GOVERNMENT,
            DeploymentContext.DEFENSE_FORWARD,
        }
        if (
            self.deployment_context in federal_contexts
            and self.bess_coupling == BessCoupling.DC_INTEGRATED_PCS
        ):
            raise ValueError(
                f"{self.deployment_context.value} + dc_integrated_pcs "
                "is not procurable (CATL exclusion)"
            )
        return self

    @model_validator(mode="after")
    def islanding_requires_bess(self) -> "ConfiguratorPayload":
        """V9: intentional islanding requires a BESS to ride through the transfer."""
        if self.grid.intentional_islanding and self.bess_coupling == BessCoupling.NONE:
            raise ValueError(
                "grid.intentional_islanding=true requires bess_coupling != none"
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
