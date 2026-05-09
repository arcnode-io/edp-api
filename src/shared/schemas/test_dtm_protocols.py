"""Protocol-level DTM schema tests — sentinel + ProvisionedInt acceptance."""

import pytest
from pydantic import ValidationError

from src.shared.schemas.dtm_protocols import (
    PROVISIONED_AT_COMMISSIONING,
    Dnp3TcpConfig,
    ProtocolKind,
    ProvisionedInt,
)


def _dnp3_cfg(
    *,
    master_addr: ProvisionedInt = 1,
    outstation_addr: ProvisionedInt = 100,
) -> Dnp3TcpConfig:
    return Dnp3TcpConfig(
        protocol=ProtocolKind.DNP3_TCP,
        master_addr=master_addr,
        outstation_addr=outstation_addr,
        point_maps=[],
    )


def test_sentinel_value() -> None:
    # Arrange / Act / Assert
    assert PROVISIONED_AT_COMMISSIONING == "PROVISIONED_AT_COMMISSIONING"


def test_dnp3_master_addr_accepts_sentinel() -> None:
    # Arrange / Act
    cfg = _dnp3_cfg(master_addr=PROVISIONED_AT_COMMISSIONING)
    # Assert
    assert cfg.master_addr == PROVISIONED_AT_COMMISSIONING


def test_dnp3_outstation_addr_accepts_sentinel() -> None:
    # Arrange / Act
    cfg = _dnp3_cfg(outstation_addr=PROVISIONED_AT_COMMISSIONING)
    # Assert
    assert cfg.outstation_addr == PROVISIONED_AT_COMMISSIONING


def test_dnp3_addrs_reject_arbitrary_string() -> None:
    # Arrange — feed a deliberately bad value via raw dict
    bad = {
        "protocol": "dnp3_tcp",
        "master_addr": "banana",
        "outstation_addr": 100,
        "point_maps": [],
    }
    # Act / Assert
    with pytest.raises(ValidationError):
        Dnp3TcpConfig.model_validate(bad)
