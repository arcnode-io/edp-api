"""Unit tests for Measurement and Command schema models, including XOR validators."""

import pytest
from pydantic import ValidationError

from src.shared.schemas.template import (
    Command,
    Fanout,
    Measurement,
    ModbusBinding,
    Publisher,
)


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
