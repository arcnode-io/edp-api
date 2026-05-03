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
    (
        DeploymentContext.SOVEREIGN_GOVERNMENT,
        BessCoupling.NONE,
    ): DeploymentProfile.FEDERAL_NO_BESS,
    (
        DeploymentContext.SOVEREIGN_GOVERNMENT,
        BessCoupling.AC_COUPLED,
    ): DeploymentProfile.FEDERAL_AC,
    (
        DeploymentContext.SOVEREIGN_GOVERNMENT,
        BessCoupling.DC_EXTERNAL_PCS,
    ): DeploymentProfile.FEDERAL_DC_EXT,
    (
        DeploymentContext.SOVEREIGN_GOVERNMENT,
        BessCoupling.DC_INTEGRATED_PCS,
    ): DeploymentProfile.FEDERAL_DC_INT,
    (
        DeploymentContext.DEFENSE_FORWARD,
        BessCoupling.NONE,
    ): DeploymentProfile.DOD_NO_BESS,
    (
        DeploymentContext.DEFENSE_FORWARD,
        BessCoupling.AC_COUPLED,
    ): DeploymentProfile.DOD_AC,
    (
        DeploymentContext.DEFENSE_FORWARD,
        BessCoupling.DC_EXTERNAL_PCS,
    ): DeploymentProfile.DOD_DC_EXT,
    # (DEFENSE_FORWARD, DC_INTEGRATED_PCS) intentionally absent — rejected at ConfiguratorPayload validator.
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
