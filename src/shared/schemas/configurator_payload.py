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
    WholesaleMarket,
)

# v1 ships ERCOT + HB_NORTH only. Other ISO/hub combos are reserved in
# the enum / form but rejected by the validator below until analyst-server
# has been validated against each ISO's gridstatus.io datasets + LMP
# settlement-point dictionaries.
_V1_SUPPORTED_HUBS: dict[WholesaleMarket, frozenset[str]] = {
    WholesaleMarket.ERCOT: frozenset({"HB_NORTH"}),
}


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

    wholesale_market: WholesaleMarket
    # Free-form so adding a new hub doesn't need a schema migration; the
    # market_hub_supported validator below pins the (ISO, hub) pair to
    # what analyst-server can actually query today.
    settlement_point: str

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
    def market_hub_supported(self) -> "ConfiguratorPayload":
        """v1 ships ERCOT + HB_NORTH only; reject other ISO/hub combos.

        Expand _V1_SUPPORTED_HUBS as analyst-server gains support for new
        ISOs (each needs its own gridstatus.io dataset id + LMP filter logic).
        """
        allowed = _V1_SUPPORTED_HUBS.get(self.wholesale_market, frozenset())
        if self.settlement_point not in allowed:
            supported = ", ".join(
                f"{market.value}={','.join(sorted(hubs))}"
                for market, hubs in _V1_SUPPORTED_HUBS.items()
            )
            raise ValueError(
                f"wholesale_market={self.wholesale_market.value} + "
                f"settlement_point={self.settlement_point!r} not supported yet. "
                f"v1 supports: {supported}"
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
