"""ConfiguratorPayload -> ModuleResolution. Pure; no external deps."""

from math import ceil

from src.module_resolver.deployment_profile import (
    EMS_TARGET_FROM_PARTITION,
    GPUS_PER_COMPUTE_CONTAINER,
    PROFILE,
    TIER_FROM_CONTEXT,
)
from src.shared.enums import BessCoupling, DeploymentProfile, EmsTarget, SourcingTier
from src.shared.schemas.configurator_payload import ConfiguratorPayload
from src.shared.schemas.module_resolution import ModuleResolution


class ModuleResolverService:
    """Resolves a ConfiguratorPayload into a ModuleResolution."""

    def resolve(self, payload: ConfiguratorPayload) -> ModuleResolution:
        """Apply decision tables + rules to produce the canonical ModuleResolution."""
        count = self._container_count(payload)
        return ModuleResolution(
            deployment_id=payload.deployment_id,
            deployment_profile=self._profile(payload),
            compute_container_count=count,
            grid_container_present=payload.bess_coupling != BessCoupling.NONE,
            bess_coupling=payload.bess_coupling,
            bess_capacity_mwh=payload.bess_capacity_mwh,
            sourcing_tier=self._sourcing_tier(payload),
            ems_target=self._ems_target(payload),
            gpu_variant=payload.gpu_variant,
            gpu_count=count * GPUS_PER_COMPUTE_CONTAINER,
            climate_zone=payload.climate_zone,
        )

    def _profile(self, payload: ConfiguratorPayload) -> DeploymentProfile:
        # Future business rules slot in here.
        return PROFILE[(payload.deployment_context, payload.bess_coupling)]

    def _container_count(self, payload: ConfiguratorPayload) -> int:
        # Future rules: tier-min container count, climate derate, etc.
        return ceil(payload.target_gpu_count / GPUS_PER_COMPUTE_CONTAINER)

    def _sourcing_tier(self, payload: ConfiguratorPayload) -> SourcingTier:
        return TIER_FROM_CONTEXT[payload.deployment_context]

    def _ems_target(self, payload: ConfiguratorPayload) -> EmsTarget:
        return EMS_TARGET_FROM_PARTITION[payload.aws_partition]
