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

GPUS_PER_COMPUTE_CONTAINER: Final[int] = 56  # 7 nodes x 8 GPUs (H100_SXM and B200)

PROFILE: Final[dict[tuple[DeploymentContext, BessCoupling], DeploymentProfile]] = {
    # Commercial — 4 hardware variants.
    (
        DeploymentContext.COMMERCIAL,
        BessCoupling.NONE,
    ): DeploymentProfile.COMMERCIAL_NO_BESS,
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
    # Sovereign government + Defense forward share the same 3 hardware
    # variants. Procurement-path differences (federal-civilian vs
    # DoD-eligible) are tracked separately by SourcingTier. dc_int is
    # rejected at the ConfiguratorPayload validator for both contexts —
    # CATL-integrated PCS isn't procurable for either.
    (
        DeploymentContext.SOVEREIGN_GOVERNMENT,
        BessCoupling.NONE,
    ): DeploymentProfile.DEFENSE_NO_BESS,
    (
        DeploymentContext.SOVEREIGN_GOVERNMENT,
        BessCoupling.AC_COUPLED,
    ): DeploymentProfile.DEFENSE_AC,
    (
        DeploymentContext.SOVEREIGN_GOVERNMENT,
        BessCoupling.DC_EXTERNAL_PCS,
    ): DeploymentProfile.DEFENSE_DC_EXT,
    (
        DeploymentContext.DEFENSE_FORWARD,
        BessCoupling.NONE,
    ): DeploymentProfile.DEFENSE_NO_BESS,
    (
        DeploymentContext.DEFENSE_FORWARD,
        BessCoupling.AC_COUPLED,
    ): DeploymentProfile.DEFENSE_AC,
    (
        DeploymentContext.DEFENSE_FORWARD,
        BessCoupling.DC_EXTERNAL_PCS,
    ): DeploymentProfile.DEFENSE_DC_EXT,
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
