"""Protocol-level template binding types.

Split out from template.py so the top-level schema stays under the file-size budget.
Owns the per-device binding models and the Binding discriminated-union alias;
module-level bindings live in template_module_bindings.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.shared.schemas.template_module_bindings import (
    DistributeBinding,
    PowerCapBinding,
    SyntheticBinding,
)


class ModbusBinding(BaseModel):
    """Modbus TCP per-measurement register slot."""

    model_config = ConfigDict(extra="forbid")

    protocol: Literal["modbus_tcp"]
    function_code: int  # 3=holding, 4=input, 6=write_single
    address: int  # 0-based protocol address, not a 4xxxxx reference number
    data_type: Literal["int16", "uint16", "int32", "uint32", "int64", "float32"]
    word_order: Literal["high_low", "low_high"] = "high_low"
    scale: float = 1.0
    offset: float = 0.0
    # SunSpec sunssf: value = raw * 10^(int16 at this register), read at runtime
    scale_factor_address: int | None = None
    value_map: dict[str, str] | None = None  # enum: raw value (as string) → label


class Dnp3Binding(BaseModel):
    """DNP3 per-measurement point reference."""

    model_config = ConfigDict(extra="forbid")

    protocol: Literal["dnp3_tcp"]
    point_index: int
    point_type: Literal[
        "analog_input", "binary_input", "analog_output", "binary_output", "counter"
    ]
    # Optional audit metadata: outstation's configured static variation
    # (e.g., 5 for Group 30 Var 5 = 32-bit float). Master polls with default
    # variation when unset; outstation's configured variation governs response.
    variation: int | None = None
    scale: float = 1.0
    value_map: dict[str, str] | None = None  # enum: raw value (as string) → label


class SnmpBinding(BaseModel):
    """SNMP per-measurement OID."""

    model_config = ConfigDict(extra="forbid")

    protocol: Literal["snmp"]
    oid: str
    scale: float = 1.0
    value_map: dict[str, str] | None = None  # enum: raw value (as string) → label


class RedfishBinding(BaseModel):
    """Redfish per-measurement resource path + JSON pointer."""

    model_config = ConfigDict(extra="forbid")

    protocol: Literal["redfish"]
    uri: str
    json_pointer: str | None = None
    scale: float = 1.0
    # enum: raw device text → label; an unmapped value is a read error
    value_map: dict[str, str] | None = None


class CanopenBinding(BaseModel):
    """CANopen-over-Ethernet per-measurement PDO mapping."""

    model_config = ConfigDict(extra="forbid")

    protocol: Literal["canopen_gw"]
    cob_id: int
    byte_offset: int
    byte_length: int


Binding = Annotated[
    ModbusBinding
    | Dnp3Binding
    | SnmpBinding
    | RedfishBinding
    | CanopenBinding
    | SyntheticBinding
    | DistributeBinding
    | PowerCapBinding,
    Field(discriminator="protocol"),
]
