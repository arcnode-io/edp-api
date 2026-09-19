"""Protocol-level template binding types.

Split out from template.py so the top-level schema stays under the file-size budget.
Owns the 5 per-measurement binding models and the Binding discriminated-union alias.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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

    Synthetic channels do NOT poll a south-side device. Exactly one of two
    input-source modes applies:

    - `inputs`: a fixed list of topics. The gateway subscribes to each,
      caches latest values, ticks at the measurement's `poll_rate_hz`, and
      publishes the result of applying `operation`. Holds (no publish) until
      every input has at least one cached sample. Topic strings may contain
      `{site_id}` (gateway runtime) and `{device_id}` (ems-device-api
      AsyncAPI-gen substitution).
    - `source_measurement`: names a measurement projected across every child
      of the device this binding lives on. Resolving children into concrete
      topics is ems-device-api's job, not modeled here.

    `weighted_mean` (capacity_kwh-weighted, per DeviceTemplate.capacity_kwh
    on each child) is only meaningful across children, so it requires
    `source_measurement` mode. `subtract` is only ever between two fixed
    topics (e.g. envelope limit minus module draw), so it requires `inputs`
    mode. `sum`/`mean`/`max`/`min` work in either mode.
    """

    model_config = ConfigDict(extra="forbid")

    protocol: Literal["synthetic"]
    operation: Literal["subtract", "sum", "mean", "max", "min", "weighted_mean"]
    inputs: list[str] | None = None
    source_measurement: str | None = None

    @model_validator(mode="after")
    def _inputs_xor_source_measurement(self) -> "SyntheticBinding":
        """Exactly one input-source mode; operation must match its mode."""
        has_inputs = self.inputs is not None
        has_source = self.source_measurement is not None
        if has_inputs == has_source:
            raise ValueError(
                "synthetic binding requires exactly one of `inputs:` (fixed "
                "topic list) or `source_measurement:` (projected across children)"
            )
        if self.operation == "weighted_mean" and not has_source:
            raise ValueError("operation=weighted_mean requires source_measurement mode")
        if self.operation == "subtract" and not has_inputs:
            raise ValueError("operation=subtract requires inputs mode")
        return self


class DistributeBinding(BaseModel):
    """Command-distribution binding — fans a module-level setpoint out to
    children per `allocation_policy`.

    No target-measurement field: verb + target are inherited from whichever
    Command this binding lives on, resolved per-child by ems-device-api
    matching verb+target against each child's own commands (not modeled here).

    The three envelope-guard fields are optional and all-or-nothing: a plain
    distribute binding (module setpoint fanout, no envelope guard) omits all
    three. When present, they carry the tunable control-law numbers for
    envelope-constrained actuation (ramp rate, hysteresis) — the concrete
    values live in ems-industrial-gateway's cfg.yml, not hardcoded; this
    schema just accepts the shape.
    """

    model_config = ConfigDict(extra="forbid")

    protocol: Literal["distribute"]
    allocation_policy: Literal["equal_split", "soc_weighted"]
    ramp_rate_per_sec: float | None = None
    hysteresis_margin: float | None = None
    hysteresis_dwell_secs: float | None = None

    @model_validator(mode="after")
    def _envelope_guard_all_or_nothing(self) -> "DistributeBinding":
        """The 3 envelope-guard fields must be all present or all absent."""
        fields = (
            self.ramp_rate_per_sec,
            self.hysteresis_margin,
            self.hysteresis_dwell_secs,
        )
        present = sum(f is not None for f in fields)
        if present not in (0, 3):
            raise ValueError(
                "distribute binding's envelope-guard fields (ramp_rate_per_sec, "
                "hysteresis_margin, hysteresis_dwell_secs) require all three or none"
            )
        return self


Binding = Annotated[
    ModbusBinding
    | Dnp3Binding
    | SnmpBinding
    | RedfishBinding
    | CanopenBinding
    | SyntheticBinding
    | DistributeBinding,
    Field(discriminator="protocol"),
]
