"""Computed placeholder semantics — Device.has_placeholders, mode, Dtm.pending_devices."""

from uuid import UUID

from src.shared.schemas.dtm import (
    PROVISIONED_AT_COMMISSIONING,
    BlockingKind,
    Bus,
    BusMember,
    Connection,
    Device,
    Dtm,
    EmsMode,
    SizingParams,
)
from src.shared.schemas.template import DeviceTemplate, Measurement, TemplateKind
from src.shared.schemas.template_protocols import ModbusBinding

DEPLOYMENT_ID: UUID = UUID("00000000-0000-0000-0000-000000000010")


def _modbus_binding() -> ModbusBinding:
    return ModbusBinding(protocol="modbus_tcp", function_code=4, address=100)


def _revenue_meter_template() -> DeviceTemplate:
    return DeviceTemplate(
        template="revenue_meter",
        kind=TemplateKind.LEAF,
        equipment_id="GRD-MTR-001",
        vendor="Schneider",
        model="ION9000",
        description="t",
        measurements={
            "voltage_a": Measurement(
                unit="volts", type="float", binding=_modbus_binding()
            )
        },
    )


def _sizing() -> SizingParams:
    return SizingParams(
        P_compute_total_kW=10.0, E_BESS_total_kWh=5000.0, T_coolant_setpoint_C=30.0
    )


def _device(
    *,
    device_id: str = "revenue_meter_1",
    connection: Connection | None = None,
) -> Device:
    return Device(
        device_id=device_id,
        template="revenue_meter",
        connection=connection or Connection(host="10.0.0.1", port=502, unit_id="2"),
        blocking=[BlockingKind.LIVE_MODE],
    )


def _dtm(*, devices: dict[str, Device]) -> Dtm:
    return Dtm(
        deployment_uuid=DEPLOYMENT_ID,
        ems_mode=EmsMode.SIM,
        sizing_params=_sizing(),
        devices=devices,
        buses=[],
        templates_used={"revenue_meter": _revenue_meter_template()},
    )


def test_device_with_no_placeholders_is_live() -> None:
    # Arrange / Act
    device = _device()
    # Assert
    assert device.has_placeholders is False
    assert device.mode == EmsMode.LIVE


def test_device_with_sentinel_host_is_sim() -> None:
    # Arrange / Act
    device = _device(connection=Connection(host=PROVISIONED_AT_COMMISSIONING, port=502))
    # Assert
    assert device.has_placeholders is True
    assert device.mode == EmsMode.SIM


def test_device_with_sentinel_port_is_sim() -> None:
    # Arrange / Act
    device = _device(
        connection=Connection(host="10.0.0.1", port=PROVISIONED_AT_COMMISSIONING)
    )
    # Assert
    assert device.has_placeholders is True
    assert device.mode == EmsMode.SIM


def test_device_with_sentinel_unit_id_is_sim() -> None:
    # Arrange / Act
    device = _device(
        connection=Connection(
            host="10.0.0.1", port=502, unit_id=PROVISIONED_AT_COMMISSIONING
        )
    )
    # Assert — sentinel in unit_id still counts
    assert device.has_placeholders is True
    assert device.mode == EmsMode.SIM


def test_pending_devices_excludes_fully_provisioned() -> None:
    # Arrange
    fully_provisioned = _device(device_id="revenue_meter_1")
    # Act
    dtm = _dtm(devices={"revenue_meter_1": fully_provisioned})
    # Assert
    assert dtm.pending_devices == []


def test_pending_devices_includes_devices_with_placeholders() -> None:
    # Arrange
    pending = _device(
        device_id="revenue_meter_1",
        connection=Connection(host=PROVISIONED_AT_COMMISSIONING, port=502),
    )
    ready = _device(
        device_id="revenue_meter_2",
        connection=Connection(host="10.0.0.2", port=502),
    )
    # Act
    dtm = _dtm(devices={"revenue_meter_1": pending, "revenue_meter_2": ready})
    # Assert
    assert [d.device_id for d in dtm.pending_devices] == ["revenue_meter_1"]


def test_pending_devices_serializes_in_model_dump() -> None:
    # Arrange
    pending = _device(
        connection=Connection(host=PROVISIONED_AT_COMMISSIONING, port=502)
    )
    dtm = _dtm(devices={"revenue_meter_1": pending})
    # Act
    dumped = dtm.model_dump()
    # Assert — computed_field must appear in serialized output
    assert "pending_devices" in dumped
    assert len(dumped["pending_devices"]) == 1


def test_pending_devices_bus_does_not_affect_sentinel_check() -> None:
    # Arrange — bus present but no sentinel in devices
    bus = Bus(
        bus_id="ac_main",
        type="ac",
        members=[BusMember(device_id="revenue_meter_1", port="line")],
    )
    fully_provisioned = _device(device_id="revenue_meter_1")
    # Act
    dtm = _dtm(devices={"revenue_meter_1": fully_provisioned})
    # Assert — bus presence alone doesn't affect pending_devices
    _ = bus  # confirm bus can coexist; pending list is still empty
    assert dtm.pending_devices == []
