"""Canonical DTM schema tests per ADR-002 §7."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from src.shared.schemas.dtm import (
    PROVISIONED_AT_COMMISSIONING,
    BlockingKind,
    Bus,
    BusMember,
    Connection,
    Device,
    Dtm,
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


def _connection() -> Connection:
    return Connection(host="10.0.0.1", port=502, unit_id="2")


def _device(
    *,
    device_id: str = "revenue_meter_1",
    template: str = "revenue_meter",
    parent: str | None = None,
    connection: Connection | None = None,
) -> Device:
    return Device(
        device_id=device_id,
        template=template,
        parent=parent,
        connection=connection or _connection(),
    )


def _sizing() -> SizingParams:
    return SizingParams(
        P_compute_total_kW=10.0, E_BESS_total_kWh=5000.0, T_coolant_setpoint_C=30.0
    )


def _dtm(
    *,
    devices: dict[str, Device] | None = None,
    buses: list[Bus] | None = None,
    templates_used: dict[str, DeviceTemplate] | None = None,
) -> Dtm:
    return Dtm(
        deployment_uuid=DEPLOYMENT_ID,
        sizing_params=_sizing(),
        devices=devices or {"revenue_meter_1": _device()},
        buses=buses or [],
        templates_used=templates_used or {"revenue_meter": _revenue_meter_template()},
    )


def test_device_id_must_be_snake_case_slug() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="slug"):
        Device(
            device_id="RevenueMeter-1",  # invalid slug
            template="revenue_meter",
            connection=_connection(),
        )


def test_device_blocking_default_is_live_mode() -> None:
    # Arrange / Act
    d = _device()
    # Assert
    assert d.blocking == [BlockingKind.LIVE_MODE]


def test_dtm_devices_keyed_by_device_id() -> None:
    # Arrange / Act
    dtm = _dtm()
    # Assert
    assert "revenue_meter_1" in dtm.devices


def test_dtm_pending_devices_excludes_fully_provisioned() -> None:
    # Arrange / Act
    dtm = _dtm()
    # Assert
    assert dtm.pending_devices == []


def test_dtm_pending_devices_includes_devices_with_sentinel() -> None:
    # Arrange
    pending = _device(
        device_id="revenue_meter_1",
        connection=Connection(host=PROVISIONED_AT_COMMISSIONING, port=502),
    )
    # Act
    dtm = _dtm(devices={"revenue_meter_1": pending})
    # Assert
    assert [d.device_id for d in dtm.pending_devices] == ["revenue_meter_1"]


def test_dtm_rejects_orphan_parent() -> None:
    # Arrange — child references a parent that's not in devices
    child = _device(device_id="revenue_meter_1", parent="grid_module_1")
    # Act / Assert
    with pytest.raises(ValidationError, match="parent"):
        _dtm(devices={"revenue_meter_1": child})


def test_dtm_rejects_orphan_template_ref() -> None:
    # Arrange — device references a template not in templates_used
    d = _device(device_id="revenue_meter_1", template="not_a_template")
    # Act / Assert
    with pytest.raises(ValidationError, match="templates_used"):
        _dtm(devices={"revenue_meter_1": d})


def test_dtm_rejects_orphan_bus_member() -> None:
    # Arrange — bus member references a device not in devices
    bus = Bus(
        bus_id="ac_main",
        type="ac",
        members=[BusMember(device_id="ghost_device", port="line")],
    )
    # Act / Assert
    with pytest.raises(ValidationError, match="bus member"):
        _dtm(buses=[bus])


def test_bus_type_dc_or_ac_only() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError):
        Bus.model_validate({"bus_id": "x", "type": "rf", "members": []})


def test_module_kind_device_has_null_connection() -> None:
    # Arrange — module template doesn't bind to a single device's protocol
    module_dev = Device(
        device_id="grid_module_1",
        template="grid_module",
        parent=None,
        connection=None,
    )
    # Assert — connection is optional and may be None
    assert module_dev.connection is None
