"""ConfiguratorPayload validator unit tests."""

from typing import TypedDict
from uuid import UUID

import pytest
from pydantic import ValidationError

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
from src.shared.schemas.configurator_payload import ConfiguratorPayload

DEPLOYMENT_ID: UUID = UUID("00000000-0000-0000-0000-000000000001")


class _PayloadKwargs(TypedDict):
    """Typed kwargs for ConfiguratorPayload construction in tests."""

    deployment_id: UUID
    operator_org: str
    deployment_site_name: str
    contact_email: str
    energy_source: EnergySource
    source_capacity_mw: float
    primary_workload: PrimaryWorkload
    gpu_variant: GpuVariant
    target_gpu_count: int
    bess_coupling: BessCoupling
    bess_capacity_mwh: float
    grid_connection: GridConnection
    climate_zone: ClimateZone
    deployment_context: DeploymentContext
    aws_partition: AwsPartition
    wholesale_market: WholesaleMarket | None
    settlement_point: str | None
    der_utility: str | None


def _kwargs(
    *,
    context: DeploymentContext = DeploymentContext.COMMERCIAL,
    coupling: BessCoupling = BessCoupling.AC_COUPLED,
    capacity_mwh: float = 5.0,
    partition: AwsPartition = AwsPartition.STANDARD,
    market: WholesaleMarket | None = WholesaleMarket.ERCOT,
    settlement_point: str | None = "HB_NORTH",
    der_utility: str | None = None,
) -> _PayloadKwargs:
    return _PayloadKwargs(
        deployment_id=DEPLOYMENT_ID,
        operator_org="acme",
        deployment_site_name="brookside dc-1",
        contact_email="ops@example.com",
        energy_source=EnergySource.GRID_HYBRID,
        source_capacity_mw=10.0,
        primary_workload=PrimaryWorkload.AI_TRAINING,
        gpu_variant=GpuVariant.H100_SXM,
        target_gpu_count=56,
        bess_coupling=coupling,
        bess_capacity_mwh=capacity_mwh,
        grid_connection=GridConnection.GRID_TIED,
        climate_zone=ClimateZone.TEMPERATE,
        deployment_context=context,
        aws_partition=partition,
        wholesale_market=market,
        settlement_point=settlement_point,
        der_utility=der_utility,
    )


def test_rejects_bess_none_with_nonzero_capacity() -> None:
    """bess_coupling=NONE + capacity>0 -> ValidationError."""
    # Arrange
    kw = _kwargs(coupling=BessCoupling.NONE, capacity_mwh=5.0)

    # Act / Assert
    with pytest.raises(
        ValidationError, match="bess_coupling=NONE iff bess_capacity_mwh=0"
    ):
        ConfiguratorPayload(**kw)


def test_rejects_bess_coupled_with_zero_capacity() -> None:
    """bess_coupling=AC_COUPLED + capacity=0 -> ValidationError."""
    # Arrange
    kw = _kwargs(coupling=BessCoupling.AC_COUPLED, capacity_mwh=0.0)

    # Act / Assert
    with pytest.raises(
        ValidationError, match="bess_coupling=NONE iff bess_capacity_mwh=0"
    ):
        ConfiguratorPayload(**kw)


def test_rejects_standard_partition_for_federal() -> None:
    """aws_partition=standard + sovereign_government -> ValidationError."""
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
    """defense_forward + dc_integrated_pcs -> ValidationError (CATL exclusion)."""
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


def test_rejects_sovereign_government_dc_integrated_pcs() -> None:
    """sovereign_government + dc_integrated_pcs -> same CATL exclusion as defense.

    Both contexts resolve to the same DEFENSE_* hardware variants, so the
    no-CATL constraint applies uniformly.
    """
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


def test_accepts_no_bess_with_zero_capacity() -> None:
    """Happy path for the no-BESS branch."""
    # Arrange
    kw = _kwargs(coupling=BessCoupling.NONE, capacity_mwh=0.0)

    # Act
    payload = ConfiguratorPayload(**kw)

    # Assert
    assert payload.bess_coupling == BessCoupling.NONE


def test_rejects_caiso_until_v2() -> None:
    """Non-ERCOT markets reserved in the enum but rejected by validator."""
    # Arrange
    kw = _kwargs(market=WholesaleMarket.CAISO, settlement_point="TH_NP15_GEN-APND")

    # Act / Assert
    with pytest.raises(ValidationError, match=r"not supported yet"):
        ConfiguratorPayload(**kw)


def test_rejects_ercot_with_unsupported_hub() -> None:
    """ERCOT is enabled but only HB_NORTH is supported in v1."""
    # Arrange
    kw = _kwargs(market=WholesaleMarket.ERCOT, settlement_point="HB_HOUSTON")

    # Act / Assert
    with pytest.raises(ValidationError, match=r"not supported yet"):
        ConfiguratorPayload(**kw)


def test_accepts_ercot_hb_north() -> None:
    """v1 happy path: ERCOT + HB_NORTH."""
    # Arrange
    kw = _kwargs(market=WholesaleMarket.ERCOT, settlement_point="HB_NORTH")

    # Act
    payload = ConfiguratorPayload(**kw)

    # Assert
    assert payload.wholesale_market == WholesaleMarket.ERCOT
    assert payload.settlement_point == "HB_NORTH"


# --- DER vs wholesale market: independent, not mutually exclusive ---


def test_neither_der_nor_wholesale_market_is_valid() -> None:
    """Off-grid / no market participation: both unset is a valid payload."""
    # Arrange
    kw = _kwargs(market=None, settlement_point=None, der_utility=None)

    # Act
    payload = ConfiguratorPayload(**kw)

    # Assert
    assert payload.wholesale_market is None
    assert payload.der_utility is None


def test_accepts_der_utility_alone() -> None:
    """DER selected, no wholesale market — der_utility is the only signal."""
    # Arrange
    kw = _kwargs(market=None, settlement_point=None, der_utility="Oncor")

    # Act
    payload = ConfiguratorPayload(**kw)

    # Assert
    assert payload.der_utility == "Oncor"
    assert payload.wholesale_market is None


def test_accepts_der_and_wholesale_market_together() -> None:
    """Both selected at once — independent, not exclusive."""
    # Arrange
    kw = _kwargs(
        market=WholesaleMarket.ERCOT, settlement_point="HB_NORTH", der_utility="Oncor"
    )

    # Act
    payload = ConfiguratorPayload(**kw)

    # Assert
    assert payload.der_utility == "Oncor"
    assert payload.wholesale_market == WholesaleMarket.ERCOT


def test_rejects_wholesale_market_without_settlement_point() -> None:
    """wholesale_market set + settlement_point unset -> ValidationError."""
    # Arrange
    kw = _kwargs(market=WholesaleMarket.ERCOT, settlement_point=None)

    # Act / Assert
    with pytest.raises(ValidationError, match="must both be set or both be unset"):
        ConfiguratorPayload(**kw)


def test_rejects_settlement_point_without_wholesale_market() -> None:
    """settlement_point set + wholesale_market unset -> ValidationError."""
    # Arrange
    kw = _kwargs(market=None, settlement_point="HB_NORTH")

    # Act / Assert
    with pytest.raises(ValidationError, match="must both be set or both be unset"):
        ConfiguratorPayload(**kw)
