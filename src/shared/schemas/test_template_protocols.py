"""Unit tests for per-protocol binding models and the discriminated-union dispatcher."""

import pytest
from pydantic import ValidationError

from src.shared.schemas.template import (
    CanopenBinding,
    Dnp3Binding,
    Measurement,
    ModbusBinding,
    RedfishBinding,
    SnmpBinding,
)


def _modbus_binding() -> ModbusBinding:
    return ModbusBinding(
        protocol="modbus_tcp", function_code=4, address=100, data_type="int16"
    )


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


def test_binding_modbus_requires_data_type() -> None:
    # Arrange / Act / Assert — no default; the gateway's differed (int32)
    with pytest.raises(ValidationError, match="data_type"):
        ModbusBinding.model_validate(
            {"protocol": "modbus_tcp", "function_code": 3, "address": 0}
        )


def test_binding_modbus_int64() -> None:
    # Arrange / Act — ION9000 energy registers are INT64 Wh
    b = ModbusBinding(
        protocol="modbus_tcp", function_code=3, address=3204, data_type="int64"
    )
    # Assert
    assert b.data_type == "int64"


def test_binding_modbus_sunspec_scale_factor() -> None:
    # Arrange / Act — SunSpec model 103: W int16 at 40084, W_SF at 40085
    b = ModbusBinding(
        protocol="modbus_tcp",
        function_code=3,
        address=40084,
        data_type="int16",
        scale_factor_address=40085,
    )
    # Assert
    assert b.scale_factor_address == 40085
    assert _modbus_binding().scale_factor_address is None


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


def test_binding_dnp3_scale() -> None:
    # Arrange / Act — SEL-351-7 reports voltage magnitudes in kV primary
    b = Dnp3Binding(
        protocol="dnp3_tcp", point_index=8, point_type="analog_input", scale=1000.0
    )
    # Assert
    assert b.scale == 1000.0
    assert (
        Dnp3Binding(protocol="dnp3_tcp", point_index=0, point_type="analog_input").scale
        == 1.0
    )


def test_binding_redfish_scale() -> None:
    # Arrange / Act — ProcessorMetrics OperatingSpeedMHz published as hertz
    b = RedfishBinding(
        protocol="redfish",
        uri="/Systems/HGX_Baseboard_0/Processors/GPU_SXM_1/ProcessorMetrics",
        json_pointer="/OperatingSpeedMHz",
        scale=1e6,
    )
    # Assert
    assert b.scale == 1e6
    assert RedfishBinding(protocol="redfish", uri="/Chassis/1").scale == 1.0


def test_binding_snmp_scale() -> None:
    # Arrange / Act — Sentry4 st4LineCurrent reports hundredth amps
    b = SnmpBinding(protocol="snmp", oid="1.3.6.1.4.1.1718.4.1.4.3.1.3", scale=0.01)
    # Assert
    assert b.scale == 0.01
    assert SnmpBinding(protocol="snmp", oid="1.3.6.1").scale == 1.0


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
            "binding": {
                "protocol": "modbus_tcp",
                "function_code": 4,
                "address": 100,
                "data_type": "int16",
            },
        }
    )
    # Assert
    assert isinstance(m.binding, ModbusBinding)
    assert m.binding.function_code == 4


def test_dnp3_binding_variation_defaults_none() -> None:
    # Arrange / Act
    b = Dnp3Binding(protocol="dnp3_tcp", point_index=0, point_type="analog_input")
    # Assert — variation is optional audit metadata
    assert b.variation is None


def test_dnp3_binding_accepts_explicit_variation() -> None:
    # Arrange / Act — Group 30 Var 5 = 32-bit float
    b = Dnp3Binding(
        protocol="dnp3_tcp", point_index=0, point_type="analog_input", variation=5
    )
    # Assert
    assert b.variation == 5
