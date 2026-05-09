"""DTM top-level schema tests — Device field validation + blocking."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from src.shared.schemas.dtm import (
    PROVISIONED_AT_COMMISSIONING,
    BlockingKind,
    Device,
    Dnp3TcpConfig,
    ModbusTcpConfig,
    PointMap,
    ProtocolKind,
    ProvisionedInt,
)

DEVICE_ID: UUID = UUID("00000000-0000-0000-0000-0000000000aa")


def _modbus_cfg() -> ModbusTcpConfig:
    return ModbusTcpConfig(
        protocol=ProtocolKind.MODBUS_TCP,
        unit_id=1,
        point_maps=[PointMap(name="soc", function_code=3, start_address=0, count=1)],
    )


def _device(
    *,
    port: ProvisionedInt = 502,
    protocol_config: ModbusTcpConfig | Dnp3TcpConfig | None = None,
    blocking: list[BlockingKind] | None = None,
) -> Device:
    return Device(
        device_uuid=DEVICE_ID,
        device_type="bms",
        module_id="grid_container_1",
        host="10.0.0.1",
        port=port,
        protocol_config=protocol_config or _modbus_cfg(),
        description="test",
        blocking=blocking if blocking is not None else [BlockingKind.LIVE_MODE],
    )


def test_blocking_kind_values() -> None:
    # Arrange / Act / Assert
    assert BlockingKind.LIVE_MODE == "live_mode"
    assert BlockingKind.COMMISSIONING_COMPLETE == "commissioning_complete"


def test_device_port_accepts_sentinel() -> None:
    # Arrange / Act
    device = _device(port=PROVISIONED_AT_COMMISSIONING)
    # Assert
    assert device.port == PROVISIONED_AT_COMMISSIONING


def test_device_port_accepts_real_int() -> None:
    # Arrange / Act
    device = _device(port=502)
    # Assert
    assert device.port == 502


def test_device_port_rejects_arbitrary_string() -> None:
    # Arrange — feed a deliberately bad value via raw dict to bypass static typing
    bad = {
        "device_uuid": str(DEVICE_ID),
        "device_type": "bms",
        "module_id": "grid_container_1",
        "host": "10.0.0.1",
        "port": "not-the-sentinel",
        "protocol_config": _modbus_cfg().model_dump(),
        "description": "test",
    }
    # Act / Assert
    with pytest.raises(ValidationError):
        Device.model_validate(bad)


def test_device_blocking_defaults_to_live_mode() -> None:
    # Arrange / Act — direct construction so we don't accidentally pass blocking
    device = Device(
        device_uuid=DEVICE_ID,
        device_type="bms",
        module_id="grid_container_1",
        host="10.0.0.1",
        port=502,
        protocol_config=_modbus_cfg(),
        description="test",
    )
    # Assert
    assert device.blocking == [BlockingKind.LIVE_MODE]


def test_device_blocking_can_be_overridden_to_empty() -> None:
    # Arrange / Act
    device = _device(blocking=[])
    # Assert
    assert device.blocking == []


def test_device_blocking_can_carry_both_kinds() -> None:
    # Arrange
    both = [BlockingKind.LIVE_MODE, BlockingKind.COMMISSIONING_COMPLETE]
    # Act
    device = _device(blocking=both)
    # Assert
    assert device.blocking == both
