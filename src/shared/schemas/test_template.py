"""Device template schema unit tests."""

import pytest
from pydantic import ValidationError

from src.shared.schemas.template import (
    CanopenBinding,
    Command,
    ContainsEntry,
    DeviceTemplate,
    Dnp3Binding,
    Fanout,
    Measurement,
    ModbusBinding,
    Publisher,
    RedfishBinding,
    SnmpBinding,
    TemplateKind,
)


def test_template_kind_values() -> None:
    # Arrange / Act / Assert
    assert TemplateKind.LEAF == "leaf"
    assert TemplateKind.MODULE == "module"


def test_publisher_values() -> None:
    # Arrange / Act / Assert
    assert Publisher.LINE_CONTROLLER == "line_controller"
    assert Publisher.ANALYST == "analyst"


def test_fanout_values() -> None:
    # Arrange / Act / Assert
    assert Fanout.LINE_CONTROLLER == "line_controller"


def test_binding_modbus_tcp() -> None:
    # Arrange / Act
    b = ModbusBinding(
        protocol="modbus_tcp",
        function_code=4,
        address=100,
        data_type="int16",
        scale=0.1,
    )
    # Assert
    assert b.protocol == "modbus_tcp"
    assert b.function_code == 4
    assert b.scale == 0.1


def test_binding_dnp3_tcp() -> None:
    # Arrange / Act
    b = Dnp3Binding(protocol="dnp3_tcp", point_index=10, point_type="analog_input")
    # Assert
    assert b.point_index == 10
    assert b.point_type == "analog_input"


def test_binding_snmp() -> None:
    # Arrange / Act
    b = SnmpBinding(protocol="snmp", oid="1.3.6.1.4.1.1718.4.1.3.3.1.7")
    # Assert
    assert b.oid == "1.3.6.1.4.1.1718.4.1.3.3.1.7"


def test_binding_redfish() -> None:
    # Arrange / Act
    b = RedfishBinding(
        protocol="redfish",
        uri="/Chassis/1/Power",
        json_pointer="/PowerControl/0/PowerConsumedWatts",
    )
    # Assert
    assert b.uri == "/Chassis/1/Power"
    assert b.json_pointer == "/PowerControl/0/PowerConsumedWatts"


def test_binding_canopen() -> None:
    # Arrange / Act
    b = CanopenBinding(
        protocol="canopen_gw", cob_id=0x180, byte_offset=0, byte_length=2
    )
    # Assert
    assert b.cob_id == 0x180
    assert b.byte_length == 2


def _modbus_binding() -> ModbusBinding:
    return ModbusBinding(protocol="modbus_tcp", function_code=4, address=100)


def test_measurement_with_binding() -> None:
    # Arrange / Act
    m = Measurement(
        unit="volts",
        type="float",
        poll_rate_hz=1.0,
        binding=_modbus_binding(),
    )
    # Assert
    assert m.unit == "volts"
    assert m.binding is not None
    assert m.publisher is None


def test_measurement_with_publisher() -> None:
    # Arrange / Act
    m = Measurement(unit="percent", type="float", publisher=Publisher.LINE_CONTROLLER)
    # Assert
    assert m.publisher == Publisher.LINE_CONTROLLER
    assert m.binding is None


def test_measurement_rejects_both_binding_and_publisher() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="exactly one of"):
        Measurement(
            unit="volts",
            type="float",
            binding=_modbus_binding(),
            publisher=Publisher.LINE_CONTROLLER,
        )


def test_measurement_rejects_neither_binding_nor_publisher() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="exactly one of"):
        Measurement(unit="volts", type="float")


def test_measurement_enum_values() -> None:
    # Arrange / Act
    m = Measurement(
        unit="none",
        type="enum",
        values={1: "AUTO", 2: "MANUAL"},
        binding=ModbusBinding(
            protocol="modbus_tcp",
            function_code=3,
            address=200,
            data_type="uint16",
        ),
    )
    # Assert
    assert m.values == {1: "AUTO", 2: "MANUAL"}


def test_command_with_binding() -> None:
    # Arrange / Act
    c = Command(
        verb="reset",
        target="counters",
        unit="none",
        payload="trigger",
        binding=ModbusBinding(protocol="modbus_tcp", function_code=6, address=300),
    )
    # Assert
    assert c.verb == "reset"


def test_command_with_fanout() -> None:
    # Arrange / Act
    c = Command(
        verb="set",
        target="active_power",
        unit="watts",
        payload="float",
        fanout=Fanout.LINE_CONTROLLER,
    )
    # Assert
    assert c.fanout == Fanout.LINE_CONTROLLER
    assert c.binding is None


def test_command_rejects_both_binding_and_fanout() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="exactly one of"):
        Command(
            verb="set",
            target="active_power",
            unit="watts",
            payload="float",
            binding=ModbusBinding(protocol="modbus_tcp", function_code=6, address=400),
            fanout=Fanout.LINE_CONTROLLER,
        )


def test_device_template_leaf_minimal() -> None:
    # Arrange / Act
    t = DeviceTemplate(
        template="revenue_meter",
        kind=TemplateKind.LEAF,
        equipment_id="GRD-MTR-001",
        vendor="Schneider Electric",
        model="ION9000",
        description="test",
        contains=[],
        measurements={
            "voltage_a": Measurement(
                unit="volts", type="float", binding=_modbus_binding()
            )
        },
    )
    # Assert
    assert t.kind == TemplateKind.LEAF
    assert t.equipment_id == "GRD-MTR-001"


def test_device_template_module_minimal() -> None:
    # Arrange / Act
    t = DeviceTemplate(
        template="bess_module",
        kind=TemplateKind.MODULE,
        description="BESS module aggregation",
        contains=[ContainsEntry(template="bess_rack", qty="scalable")],
        measurements={
            "state_of_charge": Measurement(
                unit="percent", type="float", publisher=Publisher.LINE_CONTROLLER
            )
        },
    )
    # Assert
    assert t.kind == TemplateKind.MODULE
    assert t.equipment_id is None
    assert t.contains[0].template == "bess_rack"


def test_device_template_leaf_requires_equipment_id() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="equipment_id required"):
        DeviceTemplate(
            template="revenue_meter",
            kind=TemplateKind.LEAF,
            equipment_id=None,
            description="test",
            measurements={
                "v": Measurement(unit="volts", type="float", binding=_modbus_binding())
            },
        )


def test_device_template_module_rejects_equipment_id() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="equipment_id forbidden"):
        DeviceTemplate(
            template="bess_module",
            kind=TemplateKind.MODULE,
            equipment_id="GRD-MTR-001",
            description="test",
            contains=[],
            measurements={
                "soc": Measurement(
                    unit="percent", type="float", publisher=Publisher.LINE_CONTROLLER
                )
            },
        )


def test_device_template_must_declare_measurements_or_commands() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="must declare at least one"):
        DeviceTemplate(
            template="empty",
            kind=TemplateKind.LEAF,
            equipment_id="GRD-MTR-001",
            vendor="Acme",
            model="X1",
            description="test",
        )


def test_template_slug_format_rejected() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="slug"):
        DeviceTemplate(
            template="Revenue-Meter",  # uppercase + dash → invalid
            kind=TemplateKind.LEAF,
            equipment_id="GRD-MTR-001",
            description="test",
            measurements={
                "v": Measurement(unit="volts", type="float", binding=_modbus_binding())
            },
        )


def test_device_template_leaf_requires_vendor_and_model() -> None:
    # Arrange / Act / Assert — vendor missing
    with pytest.raises(ValidationError, match="vendor required"):
        DeviceTemplate(
            template="revenue_meter",
            kind=TemplateKind.LEAF,
            equipment_id="GRD-MTR-001",
            model="ION9000",
            description="test",
            measurements={
                "v": Measurement(unit="volts", type="float", binding=_modbus_binding())
            },
        )
    # model missing
    with pytest.raises(ValidationError, match="model required"):
        DeviceTemplate(
            template="revenue_meter",
            kind=TemplateKind.LEAF,
            equipment_id="GRD-MTR-001",
            vendor="Schneider",
            description="test",
            measurements={
                "v": Measurement(unit="volts", type="float", binding=_modbus_binding())
            },
        )


def test_device_template_module_rejects_vendor_and_model() -> None:
    # Arrange / Act / Assert — vendor present on module
    with pytest.raises(ValidationError, match="vendor forbidden"):
        DeviceTemplate(
            template="bess_module",
            kind=TemplateKind.MODULE,
            vendor="Acme",
            description="test",
            measurements={
                "soc": Measurement(
                    unit="percent", type="float", publisher=Publisher.LINE_CONTROLLER
                )
            },
        )
    # model present on module
    with pytest.raises(ValidationError, match="model forbidden"):
        DeviceTemplate(
            template="bess_module",
            kind=TemplateKind.MODULE,
            model="X1",
            description="test",
            measurements={
                "soc": Measurement(
                    unit="percent", type="float", publisher=Publisher.LINE_CONTROLLER
                )
            },
        )


def test_device_template_leaf_rejects_contains() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="contains forbidden"):
        DeviceTemplate(
            template="revenue_meter",
            kind=TemplateKind.LEAF,
            equipment_id="GRD-MTR-001",
            vendor="Schneider",
            model="ION9000",
            description="test",
            contains=[ContainsEntry(template="sub_module", qty=1)],
            measurements={
                "v": Measurement(unit="volts", type="float", binding=_modbus_binding())
            },
        )


def test_measurement_enum_requires_values() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="type=enum requires values"):
        Measurement(unit="none", type="enum", binding=_modbus_binding())


def test_measurement_non_enum_rejects_values() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="values forbidden for non-enum type"):
        Measurement(
            unit="volts",
            type="float",
            values={1: "HIGH", 2: "LOW"},
            binding=_modbus_binding(),
        )


def test_measurement_binding_dict_dispatches_to_modbus() -> None:
    # Arrange / Act — validate from dict so discriminator resolves protocol → ModbusBinding
    m = Measurement.model_validate(
        {
            "unit": "volts",
            "type": "float",
            "binding": {"protocol": "modbus_tcp", "function_code": 4, "address": 100},
        }
    )
    # Assert
    assert isinstance(m.binding, ModbusBinding)
    assert m.binding.function_code == 4
