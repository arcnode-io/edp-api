"""Alarm catalog primitives — mirror of equipment_spec.alarms[] shape.

Source of truth: `equipment_spec_schema.md §4.4.6` in edp-module-assemblies.
Pydantic implementation here mirrors the canonical models at
`edp-module-assemblies/src/alarms/alarm_spec.py`; Zod implementation
mirrors the same shape at `ems-device-api/src/templates/template.alarms.schema.ts`.

The three implementations must stay structurally identical — the contract
is the YAML/JSON shape, not Python imports across repos.

These models are referenced from `DeviceTemplate.alarms[]` so the DTM
carries the per-SKU alarm catalog. The DTM generator loads them from
each device's equipment_spec.yaml at build time.
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class AlarmPriority(StrEnum):
    """4-tier alarm priority per Hollifield §7.19."""

    P1 = "P1"  # safety / people
    P2 = "P2"  # equipment damage avoidance
    P3 = "P3"  # process deviation
    P4 = "P4"  # diagnostic / advisory


class Reset(StrEnum):
    """Clear behavior when the underlying condition returns to normal."""

    LATCHED = "latched"
    AUTO = "auto"


class DiscreteRegisterSource(BaseModel):
    """One Modbus discrete/holding register bit is the trigger."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["discrete_register"]
    address: int = Field(ge=0)
    meaning_when_set: Literal["alarm", "clear"]


class AnalogThresholdSource(BaseModel):
    """Modbus analog register crosses a threshold."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["analog_threshold"]
    address: int = Field(ge=0)
    threshold: float
    direction: Literal["above", "below"]
    unit: str
    deadband_pct: float | None = Field(default=None, ge=0)


class SnmpTrapSource(BaseModel):
    """SNMP trap OID is the trigger."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["snmp_trap"]
    oid: str


class DnpEventSource(BaseModel):
    """DNP3 event point is the trigger."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["dnp_event"]
    point_index: int = Field(ge=0)
    point_type: Literal["binary_input", "analog_input"]


class RedfishEventSource(BaseModel):
    """Redfish event identifier is the trigger."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["redfish_event"]
    event_id: str
    severity: Literal["OK", "Warning", "Critical"] | None = None


ConditionSource = Annotated[
    DiscreteRegisterSource
    | AnalogThresholdSource
    | SnmpTrapSource
    | DnpEventSource
    | RedfishEventSource,
    Field(discriminator="type"),
]


class Alarm(BaseModel):
    """One alarm definition per Hollifield D&R rationalization step."""

    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    condition_source: ConditionSource
    priority: AlarmPriority
    operator_action: str
    on_delay_ms: int = Field(ge=0)
    off_delay_ms: int = Field(ge=0)
    reset: Reset
    reference_doc: str


def load_alarms_from_spec(spec_dict: dict) -> list[Alarm]:
    """Parse `spec.alarms[]` from a loaded equipment_spec.yaml dict.

    Returns [] when the SKU has no alarm catalog yet (specs migrate
    incrementally). Raises ValidationError on malformed entries.
    """
    alarms_raw = spec_dict.get("spec", {}).get("alarms") or []
    return [Alarm.model_validate(a) for a in alarms_raw]
