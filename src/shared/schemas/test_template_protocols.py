"""Unit tests for per-protocol binding models and the discriminated-union dispatcher."""

import pytest
from pydantic import ValidationError

from src.shared.schemas.template import (
    CanopenBinding,
    DistributeBinding,
    Dnp3Binding,
    Measurement,
    ModbusBinding,
    Publisher,
    RedfishBinding,
    SnmpBinding,
    SyntheticBinding,
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


def test_binding_distribute_equal_split() -> None:
    # Arrange / Act
    b = DistributeBinding(protocol="distribute", allocation_policy="equal_split")
    # Assert
    assert b.allocation_policy == "equal_split"


def test_binding_distribute_soc_weighted() -> None:
    # Arrange / Act
    b = DistributeBinding(protocol="distribute", allocation_policy="soc_weighted")
    # Assert
    assert b.allocation_policy == "soc_weighted"


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


def test_synthetic_binding_happy_path() -> None:
    # Arrange / Act
    b = SyntheticBinding(
        protocol="synthetic",
        operation="subtract",
        inputs=[
            "sites/{site_id}/devices/operating_envelope/measurements/import_limit/watts",
            "sites/{site_id}/devices/{device_id}/measurements/active_power/watts",
        ],
    )
    # Assert
    assert b.operation == "subtract"
    assert b.inputs is not None
    assert len(b.inputs) == 2


def test_synthetic_binding_source_measurement_mode() -> None:
    # Arrange / Act — projects one measurement across the device's children
    b = SyntheticBinding(
        protocol="synthetic",
        operation="weighted_mean",
        source_measurement="state_of_charge",
    )
    # Assert
    assert b.operation == "weighted_mean"
    assert b.source_measurement == "state_of_charge"
    assert b.inputs is None


def test_synthetic_binding_rejects_both_inputs_and_source_measurement() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="exactly one of"):
        SyntheticBinding(
            protocol="synthetic",
            operation="sum",
            inputs=["a", "b"],
            source_measurement="active_power",
        )


def test_synthetic_binding_rejects_neither_inputs_nor_source_measurement() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="exactly one of"):
        SyntheticBinding(protocol="synthetic", operation="sum")


def test_synthetic_binding_weighted_mean_requires_source_measurement_mode() -> None:
    # Arrange / Act / Assert — weighted_mean can't pair with a fixed inputs list
    with pytest.raises(ValidationError, match="weighted_mean requires"):
        SyntheticBinding(
            protocol="synthetic", operation="weighted_mean", inputs=["a", "b"]
        )


def test_synthetic_binding_subtract_requires_inputs_mode() -> None:
    # Arrange / Act / Assert — subtract can't pair with source_measurement
    with pytest.raises(ValidationError, match="subtract requires"):
        SyntheticBinding(
            protocol="synthetic",
            operation="subtract",
            source_measurement="active_power",
        )


def test_synthetic_binding_sum_valid_in_source_measurement_mode() -> None:
    # Arrange / Act — sum/mean/max/min work in either mode
    b = SyntheticBinding(
        protocol="synthetic", operation="sum", source_measurement="active_power"
    )
    # Assert
    assert b.operation == "sum"


def test_synthetic_measurement_requires_publisher_gateway() -> None:
    # Arrange / Act / Assert — synthetic binding without publisher = invalid
    with pytest.raises(
        ValidationError, match=r"binding\.protocol=synthetic requires publisher=gateway"
    ):
        Measurement(
            unit="watts",
            type="float",
            binding=SyntheticBinding(
                protocol="synthetic", operation="subtract", inputs=["a", "b"]
            ),
        )


def test_synthetic_measurement_rejects_non_gateway_publisher() -> None:
    # Arrange / Act / Assert — publisher must be GATEWAY when binding is synthetic
    with pytest.raises(
        ValidationError, match=r"binding\.protocol=synthetic requires publisher=gateway"
    ):
        Measurement(
            unit="watts",
            type="float",
            binding=SyntheticBinding(
                protocol="synthetic", operation="subtract", inputs=["a", "b"]
            ),
            publisher=Publisher.LOCAL_PROCESS,
        )


def test_synthetic_measurement_with_gateway_publisher_validates() -> None:
    # Arrange / Act
    m = Measurement(
        unit="watts",
        type="float",
        binding=SyntheticBinding(
            protocol="synthetic", operation="subtract", inputs=["a", "b"]
        ),
        publisher=Publisher.GATEWAY,
    )
    # Assert
    assert isinstance(m.binding, SyntheticBinding)
    assert m.publisher == Publisher.GATEWAY
