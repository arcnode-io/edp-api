"""Protocol-level template binding types.

Split out from template.py so the top-level schema stays under the file-size budget.
Owns the 5 per-measurement binding models and the Binding discriminated-union alias.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ModbusBinding(BaseModel):
    """Modbus TCP per-measurement register slot."""

    protocol: Literal["modbus_tcp"]
    function_code: int  # 3=holding, 4=input, 6=write_single
    address: int
    data_type: Literal["int16", "uint16", "int32", "uint32", "float32"] = "int16"
    word_order: Literal["high_low", "low_high"] = "high_low"
    scale: float = 1.0
    offset: float = 0.0


class Dnp3Binding(BaseModel):
    """DNP3 per-measurement point reference."""

    protocol: Literal["dnp3_tcp"]
    point_index: int
    point_type: Literal[
        "analog_input", "binary_input", "analog_output", "binary_output", "counter"
    ]


class SnmpBinding(BaseModel):
    """SNMP per-measurement OID."""

    protocol: Literal["snmp"]
    oid: str


class RedfishBinding(BaseModel):
    """Redfish per-measurement resource path + JSON pointer."""

    protocol: Literal["redfish"]
    uri: str
    json_pointer: str | None = None


class CanopenBinding(BaseModel):
    """CANopen-over-Ethernet per-measurement PDO mapping."""

    protocol: Literal["canopen_gw"]
    cob_id: int
    byte_offset: int
    byte_length: int


Binding = Annotated[
    ModbusBinding | Dnp3Binding | SnmpBinding | RedfishBinding | CanopenBinding,
    Field(discriminator="protocol"),
]
