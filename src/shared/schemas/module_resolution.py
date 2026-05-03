"""Resolved module config — output of module_resolver, input to every generator."""

from uuid import UUID

from pydantic import BaseModel, Field

from src.shared.enums import (
    BessCoupling,
    ClimateZone,
    DeploymentProfile,
    EmsTarget,
    GpuVariant,
    SourcingTier,
)


class ModuleResolution(BaseModel):
    """Canonical input to BOM, DTM, drawing, installation_graph, hardware_selector."""

    deployment_id: UUID

    deployment_profile: DeploymentProfile

    compute_container_count: int = Field(ge=1)
    grid_container_present: bool

    bess_coupling: BessCoupling
    bess_capacity_mwh: float

    sourcing_tier: SourcingTier
    ems_target: EmsTarget

    gpu_variant: GpuVariant
    gpu_count: int
    climate_zone: ClimateZone
