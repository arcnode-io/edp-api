"""Minimal template dicts for schema tests; import explicitly."""

from src.shared.schemas.template import (
    Measurement,
    ModbusBinding,
    Publisher,
)


def _mb() -> ModbusBinding:
    return ModbusBinding(
        protocol="modbus_tcp", function_code=4, address=100, data_type="int16"
    )


def _mv() -> dict[str, Measurement]:
    """Single float voltage measurement — reused across validator tests."""
    return {"v": Measurement(unit="volts", type="float", binding=_mb())}


def _ms() -> dict[str, Measurement]:
    """Single publisher SOC measurement — reused in module validator tests."""
    return {
        "soc": Measurement(
            unit="percent", type="float", publisher=Publisher.LOCAL_PROCESS
        )
    }
