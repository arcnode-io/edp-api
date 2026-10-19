"""Decision tables for resolving DeploymentProfile + derived enums.

Pure data. Logic lives in module_resolver_service.
"""

from typing import Final

from src.shared.enums import (
    AwsPartition,
    BessCoupling,
    DeploymentContext,
    DeploymentProfile,
    EmsTarget,
    SourcingTier,
)

GPUS_PER_NODE: Final[int] = 8  # one HGX board (H100_SXM and B200)
NODES_PER_COMPUTE_CONTAINER: Final[int] = 7  # a full container; the last may hold fewer

PROFILE: Final[dict[tuple[DeploymentContext, BessCoupling], DeploymentProfile]] = {
    # Commercial — 3 hardware variants, one per BESS coupling.
    (
        DeploymentContext.COMMERCIAL,
        BessCoupling.AC_COUPLED,
    ): DeploymentProfile.COMMERCIAL_AC,
    (
        DeploymentContext.COMMERCIAL,
        BessCoupling.DC_EXTERNAL_PCS,
    ): DeploymentProfile.COMMERCIAL_DC_EXT,
    (
        DeploymentContext.COMMERCIAL,
        BessCoupling.DC_INTEGRATED_PCS,
    ): DeploymentProfile.COMMERCIAL_DC_INT,
    # Sovereign government + Defense forward share the one AC hardware
    # variant. Procurement-path differences (federal-civilian vs
    # DoD-eligible) are tracked separately by SourcingTier. Both DC
    # couplings are rejected at the ConfiguratorPayload validator for these
    # contexts — our DC batteries are CATL (DOD 1260H).
    (
        DeploymentContext.SOVEREIGN_GOVERNMENT,
        BessCoupling.AC_COUPLED,
    ): DeploymentProfile.DEFENSE_AC,
    (
        DeploymentContext.DEFENSE_FORWARD,
        BessCoupling.AC_COUPLED,
    ): DeploymentProfile.DEFENSE_AC,
}

TIER_FROM_CONTEXT: Final[dict[DeploymentContext, SourcingTier]] = {
    DeploymentContext.COMMERCIAL: SourcingTier.COMMERCIAL,
    DeploymentContext.SOVEREIGN_GOVERNMENT: SourcingTier.FEDERAL_CIVILIAN,
    DeploymentContext.DEFENSE_FORWARD: SourcingTier.DOD_ELIGIBLE,
}

EMS_TARGET_FROM_PARTITION: Final[dict[AwsPartition, EmsTarget]] = {
    AwsPartition.STANDARD: EmsTarget.AWS_STANDARD,
    AwsPartition.GOVCLOUD: EmsTarget.AWS_GOVCLOUD,
    AwsPartition.NONE: EmsTarget.AIR_GAPPED,
}
