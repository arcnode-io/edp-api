"""Customer-submitted configuration. Forwarded verbatim from platform-api."""

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator

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


class ConfiguratorPayload(BaseModel):
    """Single source of truth for a deployment's user-supplied configuration."""

    deployment_id: UUID

    operator_org: str
    deployment_site_name: str
    contact_email: EmailStr

    energy_source: EnergySource
    source_capacity_mw: float = Field(gt=0)

    primary_workload: PrimaryWorkload
    gpu_variant: GpuVariant
    target_gpu_count: int = Field(ge=1)

    bess_coupling: BessCoupling
    bess_capacity_mwh: float = Field(ge=0)

    grid_connection: GridConnection
    climate_zone: ClimateZone
    deployment_context: DeploymentContext
    aws_partition: AwsPartition

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
    def dod_excludes_dc_integrated_pcs(self) -> "ConfiguratorPayload":
        """Reject defense_forward + dc_integrated_pcs (CATL exclusion)."""
        # Reason: integrated DC PCS is CATL-only; CATL excluded from DoD procurement.
        if (
            self.deployment_context == DeploymentContext.DEFENSE_FORWARD
            and self.bess_coupling == BessCoupling.DC_INTEGRATED_PCS
        ):
            raise ValueError(
                "defense_forward + dc_integrated_pcs is not procurable (CATL exclusion)"
            )
        return self
