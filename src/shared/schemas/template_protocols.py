"""Protocol-level template binding types.

Split out from template.py so the top-level schema stays under the file-size budget.
Owns the 5 per-measurement binding models and the Binding discriminated-union alias.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class ModbusBinding(BaseModel):
    """Modbus TCP per-measurement register slot."""

    model_config = ConfigDict(extra="forbid")

    protocol: Literal["modbus_tcp"]
    function_code: int  # 3=holding, 4=input, 6=write_single
    address: int
    data_type: Literal["int16", "uint16", "int32", "uint32", "float32"] = "int16"
    word_order: Literal["high_low", "low_high"] = "high_low"
    scale: float = 1.0
    offset: float = 0.0


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


class SnmpBinding(BaseModel):
    """SNMP per-measurement OID."""

    model_config = ConfigDict(extra="forbid")

    protocol: Literal["snmp"]
    oid: str


class RedfishBinding(BaseModel):
    """Redfish per-measurement resource path + JSON pointer."""

    model_config = ConfigDict(extra="forbid")

    protocol: Literal["redfish"]
    uri: str
    json_pointer: str | None = None


class CanopenBinding(BaseModel):
    """CANopen-over-Ethernet per-measurement PDO mapping."""

    model_config = ConfigDict(extra="forbid")

    protocol: Literal["canopen_gw"]
    cob_id: int
    byte_offset: int
    byte_length: int


class SyntheticBinding(BaseModel):
    """Gateway-side pure-function derivation from cached MQTT inputs.

    Synthetic channels do NOT poll a south-side device. The gateway subscribes
    to the topics listed in `inputs`, caches latest values per topic, ticks at
    the measurement's `poll_rate_hz`, and publishes the result of applying
    `formula` to the cached input values. Holds (no publish) until every
    input has at least one cached sample.

    Input topic strings may contain `{site_id}` (substituted at gateway runtime
    from deployment config) and `{device_id}` (substituted at ems-device-api
    AsyncAPI generation time with the instantiating device's id).
    """

    model_config = ConfigDict(extra="forbid")

    protocol: Literal["synthetic"]
    formula: Literal["subtract", "sum", "mean", "max", "min"]
    inputs: list[str]


Binding = Annotated[
    ModbusBinding
    | Dnp3Binding
    | SnmpBinding
    | RedfishBinding
    | CanopenBinding
    | SyntheticBinding,
    Field(discriminator="protocol"),
]
