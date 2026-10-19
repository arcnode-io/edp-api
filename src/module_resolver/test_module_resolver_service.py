"""ModuleResolverService unit tests. AAA pattern, table-driven over the 11 profiles."""

import pytest

from src.module_resolver.module_resolver_service import ModuleResolverService
from src.shared.enums import (
    AwsPartition,
    BessCoupling,
    DeploymentContext,
    DeploymentProfile,
    EmsTarget,
    SourcingTier,
)
from src.module_resolver.module_resolver_test_support import (
    _payload,
)


def test_resolves_commercial_ac_profile() -> None:
    """Happy path: commercial + ac_coupled -> COMMERCIAL_AC."""
    # Arrange
    service = ModuleResolverService()
    payload = _payload()

    # Act
    actual = service.resolve(payload)

    # Assert
    assert actual.deployment_profile == DeploymentProfile.COMMERCIAL_AC


# 6 valid combos -> 4 profiles. Drives the matrix exhaustively.
_PROFILE_CASES: list[
    tuple[DeploymentContext, BessCoupling, AwsPartition, DeploymentProfile]
] = [
    (
        DeploymentContext.COMMERCIAL,
        BessCoupling.AC_COUPLED,
        AwsPartition.STANDARD,
        DeploymentProfile.COMMERCIAL_AC,
    ),
    (
        DeploymentContext.COMMERCIAL,
        BessCoupling.DC_EXTERNAL_PCS,
        AwsPartition.STANDARD,
        DeploymentProfile.COMMERCIAL_DC_EXT,
    ),
    (
        DeploymentContext.COMMERCIAL,
        BessCoupling.DC_INTEGRATED_PCS,
        AwsPartition.STANDARD,
        DeploymentProfile.COMMERCIAL_DC_INT,
    ),
    # Sovereign government — same hardware as defense_forward; SourcingTier
    # distinguishes procurement path (federal_civilian vs dod_eligible).
    (
        DeploymentContext.SOVEREIGN_GOVERNMENT,
        BessCoupling.AC_COUPLED,
        AwsPartition.GOVCLOUD,
        DeploymentProfile.DEFENSE_AC,
    ),
    # Federal + either DC coupling intentionally absent — rejected at the
    # ConfiguratorPayload validator (CATL exclusion).
    (
        DeploymentContext.DEFENSE_FORWARD,
        BessCoupling.AC_COUPLED,
        AwsPartition.NONE,
        DeploymentProfile.DEFENSE_AC,
    ),
]


@pytest.mark.parametrize(
    ("context", "coupling", "partition", "expected"), _PROFILE_CASES
)
def test_resolves_full_profile_matrix(
    context: DeploymentContext,
    coupling: BessCoupling,
    partition: AwsPartition,
    expected: DeploymentProfile,
) -> None:
    """Every valid (context, coupling) combo resolves to the expected profile."""
    # Arrange
    service = ModuleResolverService()
    payload = _payload(context=context, coupling=coupling, partition=partition)

    # Act
    actual = service.resolve(payload)

    # Assert
    assert actual.deployment_profile == expected


def test_derives_sourcing_tier_and_ems_target() -> None:
    """sovereign_government + govcloud -> federal_civilian + aws_govcloud."""
    # Arrange
    service = ModuleResolverService()
    payload = _payload(
        context=DeploymentContext.SOVEREIGN_GOVERNMENT,
        partition=AwsPartition.GOVCLOUD,
    )

    # Act
    actual = service.resolve(payload)

    # Assert
    assert actual.sourcing_tier == SourcingTier.FEDERAL_CIVILIAN
    assert actual.ems_target == EmsTarget.AWS_GOVCLOUD


def test_carries_the_site_compute_shed_choice() -> None:
    """compute_shed_enabled is a per-site order-time choice, passed through."""
    # Arrange
    service = ModuleResolverService()
    payload = _payload().model_copy(update={"compute_shed_enabled": True})
    # Act
    actual = service.resolve(payload)
    # Assert
    assert actual.compute_shed_enabled is True
