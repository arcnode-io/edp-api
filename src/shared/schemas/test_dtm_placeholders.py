"""Computed placeholder semantics — Device.has_placeholders, mode, Dtm.pending_devices."""

from uuid import UUID

from src.shared.schemas.dtm import (
    PROVISIONED_AT_COMMISSIONING,
    BlockingKind,
    Device,
    Dnp3TcpConfig,
    Dtm,
    EmsMode,
    ModbusTcpConfig,
    Module,
    PointMap,
    ProtocolKind,
    ProvisionedInt,
    SizingParams,
)

DEPLOYMENT_ID: UUID = UUID("00000000-0000-0000-0000-000000000010")
DEVICE_ID: UUID = UUID("00000000-0000-0000-0000-0000000000aa")
DEVICE_ID_B: UUID = UUID("00000000-0000-0000-0000-0000000000bb")


def _sizing() -> SizingParams:
    return SizingParams(
        P_compute_total_kW=10.0, E_BESS_total_kWh=5000.0, T_coolant_setpoint_C=30.0
    )


def _modbus_cfg() -> ModbusTcpConfig:
    return ModbusTcpConfig(
        protocol=ProtocolKind.MODBUS_TCP,
        unit_id=1,
        point_maps=[PointMap(name="soc", function_code=3, start_address=0, count=1)],
    )


def _dnp3_cfg_with_sentinel_master() -> Dnp3TcpConfig:
    return Dnp3TcpConfig(
        protocol=ProtocolKind.DNP3_TCP,
        master_addr=PROVISIONED_AT_COMMISSIONING,
        outstation_addr=100,
        point_maps=[],
    )


def _module() -> Module:
    return Module(
        module_id="grid_container_1",
        module_type="grid_container",
        container_position="position_grid",
        description="grid",
    )


def _device(
    *,
    device_uuid: UUID = DEVICE_ID,
    host: str = "10.0.0.1",
    port: ProvisionedInt = 502,
    protocol_config: ModbusTcpConfig | Dnp3TcpConfig | None = None,
) -> Device:
    return Device(
        device_uuid=device_uuid,
        device_type="bms",
        module_id="grid_container_1",
        host=host,
        port=port,
        protocol_config=protocol_config or _modbus_cfg(),
        description="test",
        blocking=[BlockingKind.LIVE_MODE],
    )


def _dtm(*, devices: list[Device]) -> Dtm:
    return Dtm(
        deployment_uuid=DEPLOYMENT_ID,
        ems_mode=EmsMode.SIM,
        sizing_params=_sizing(),
        modules=[_module()],
        devices=devices,
    )


def test_device_with_no_placeholders_is_live() -> None:
    # Arrange / Act
    device = _device()
    # Assert
    assert device.has_placeholders is False
    assert device.mode == EmsMode.LIVE


def test_device_with_sentinel_host_is_sim() -> None:
    # Arrange / Act
    device = _device(host=PROVISIONED_AT_COMMISSIONING)
    # Assert
    assert device.has_placeholders is True
    assert device.mode == EmsMode.SIM


def test_device_with_sentinel_port_is_sim() -> None:
    # Arrange / Act
    device = _device(port=PROVISIONED_AT_COMMISSIONING)
    # Assert
    assert device.has_placeholders is True
    assert device.mode == EmsMode.SIM


def test_device_with_sentinel_in_protocol_config_is_sim() -> None:
    # Arrange
    cfg = _dnp3_cfg_with_sentinel_master()
    # Act
    device = _device(protocol_config=cfg)
    # Assert — placeholder buried inside protocol_config still counts
    assert device.has_placeholders is True
    assert device.mode == EmsMode.SIM


def test_pending_devices_excludes_fully_provisioned() -> None:
    # Arrange
    fully_provisioned = _device(device_uuid=DEVICE_ID)
    # Act
    dtm = _dtm(devices=[fully_provisioned])
    # Assert
    assert dtm.pending_devices == []


def test_pending_devices_includes_devices_with_placeholders() -> None:
    # Arrange
    pending = _device(device_uuid=DEVICE_ID, host=PROVISIONED_AT_COMMISSIONING)
    ready = _device(device_uuid=DEVICE_ID_B)
    # Act
    dtm = _dtm(devices=[pending, ready])
    # Assert
    assert [d.device_uuid for d in dtm.pending_devices] == [DEVICE_ID]


def test_pending_devices_serializes_in_model_dump() -> None:
    # Arrange
    pending = _device(host=PROVISIONED_AT_COMMISSIONING)
    dtm = _dtm(devices=[pending])
    # Act
    dumped = dtm.model_dump()
    # Assert — computed_field should appear in serialized output
    assert "pending_devices" in dumped
    assert len(dumped["pending_devices"]) == 1
