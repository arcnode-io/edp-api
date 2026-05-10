"""Unit tests for per-protocol binding models and the discriminated-union dispatcher."""

from src.shared.schemas.template import (
    CanopenBinding,
    Dnp3Binding,
    Measurement,
    ModbusBinding,
    RedfishBinding,
    SnmpBinding,
)


def _modbus_binding() -> ModbusBinding:
    return ModbusBinding(protocol="modbus_tcp", function_code=4, address=100)


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
