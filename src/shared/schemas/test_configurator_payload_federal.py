"""Federal/defense orders: partition and CATL (DC coupling) exclusions."""

import pytest
from pydantic import ValidationError

from src.shared.enums import (
    AwsPartition,
    BessCoupling,
    DeploymentContext,
)
from src.shared.schemas.configurator_payload import ConfiguratorPayload
from src.shared.schemas.configurator_payload_test_support import (
    _kwargs,
)


def test_rejects_standard_partition_for_federal() -> None:
    # Arrange
    kw = _kwargs(
        context=DeploymentContext.SOVEREIGN_GOVERNMENT,
        partition=AwsPartition.STANDARD,
    )

    # Act / Assert
    with pytest.raises(
        ValidationError,
        match="aws_partition=standard only valid for deployment_context=commercial",
    ):
        ConfiguratorPayload(**kw)


def test_rejects_defense_forward_dc_integrated_pcs() -> None:
    # Arrange
    kw = _kwargs(
        context=DeploymentContext.DEFENSE_FORWARD,
        coupling=BessCoupling.DC_INTEGRATED_PCS,
        capacity_mwh=5.0,
        partition=AwsPartition.NONE,
    )

    # Act / Assert
    with pytest.raises(ValidationError, match="CATL exclusion"):
        ConfiguratorPayload(**kw)


@pytest.mark.parametrize(
    "context",
    [DeploymentContext.SOVEREIGN_GOVERNMENT, DeploymentContext.DEFENSE_FORWARD],
)
def test_rejects_federal_dc_external_pcs(context: DeploymentContext) -> None:
    """The only DC battery we spec is CATL EnerOne+, on DOD 1260H."""
    # Arrange
    kw = _kwargs(
        context=context,
        coupling=BessCoupling.DC_EXTERNAL_PCS,
        capacity_mwh=5.0,
        partition=AwsPartition.GOVCLOUD,
    )

    # Act / Assert
    with pytest.raises(ValidationError, match="CATL exclusion"):
        ConfiguratorPayload(**kw)


def test_rejects_sovereign_government_dc_integrated_pcs() -> None:
    """Both federal contexts resolve to the same DEFENSE_* hardware variants."""
    # Arrange
    kw = _kwargs(
        context=DeploymentContext.SOVEREIGN_GOVERNMENT,
        coupling=BessCoupling.DC_INTEGRATED_PCS,
        capacity_mwh=5.0,
        partition=AwsPartition.GOVCLOUD,
    )

    # Act / Assert
    with pytest.raises(ValidationError, match="CATL exclusion"):
        ConfiguratorPayload(**kw)
