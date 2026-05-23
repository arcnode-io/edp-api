"""Device template schema — canonical vocabulary per ADR-002 §7.

Templates own per-measurement protocol bindings (Modbus FC, DNP3 addrs,
SNMP OIDs). DTMs reference templates by slug; per-instance Devices contribute
deployment specifics (host, port, parent, display_name).
Protocol-level binding types live in template_protocols.py; the Measurement
channel + its Publisher live in measurement.py; range/threshold types live in
measurement_ranges.py. This module re-exports the full surface so existing
imports keep working.
"""

import re
from enum import StrEnum
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.shared.schemas.measurement import Measurement, Publisher
from src.shared.schemas.measurement_ranges import Bounds, Thresholds
from src.shared.schemas.template_protocols import (
    Binding,
    CanopenBinding,
    Dnp3Binding,
    ModbusBinding,
    RedfishBinding,
    SnmpBinding,
    SyntheticBinding,
)

__all__ = [
    "Binding",
    "Bounds",
    "CanopenBinding",
    "Command",
    "ContainsEntry",
    "DeviceTemplate",
    "Dnp3Binding",
    "Fanout",
    "Measurement",
    "ModbusBinding",
    "Publisher",
    "RedfishBinding",
    "SnmpBinding",
    "SyntheticBinding",
    "TemplateKind",
    "Thresholds",
]

_SLUG_RE: Final = re.compile(r"^[a-z][a-z0-9_]{0,62}[a-z0-9]$")


class TemplateKind(StrEnum):
    """Leaf templates have equipment_id; modules are aggregations with contains."""

    LEAF = "leaf"
    MODULE = "module"


class Fanout(StrEnum):
    """Who handles a command that has no direct binding (fans out to children)."""

    LINE_CONTROLLER = "line_controller"


class Command(BaseModel):
    """One channel a device receives. Either bound to a protocol or
    fanned out by line-controller."""

    model_config = ConfigDict(extra="forbid")

    verb: Literal["set", "reset", "clear", "start", "stop", "enable", "disable"]
    target: str
    unit: str
    payload: Literal["float", "bool", "enum", "trigger"]
    display_name_default: str | None = None
    binding: Binding | None = None
    fanout: Fanout | None = None

    @model_validator(mode="after")
    def _binding_xor_fanout(self) -> "Command":
        """Each command MUST have exactly one of binding or fanout."""
        has_binding = self.binding is not None
        has_fanout = self.fanout is not None
        if has_binding == has_fanout:
            raise ValueError(
                "command requires exactly one of `binding:` (gateway-bound) "
                "or `fanout:` (line-controller-handled)"
            )
        return self


class ContainsEntry(BaseModel):
    """Reference to a child template inside a module's contains[].

    `power_from` names sibling `contains[].template` slugs that supply
    AC power to this entry. Empty list = doesn't draw power (e.g. PDUs
    themselves, sensors). Multi-entry list = 2N or N+1 redundant feeds;
    v1 cable schedule emits one row (primary feed) and parks the
    redundant-feed row for v2 when feed-side designators (A/B) live on
    PDU instances.
    """

    model_config = ConfigDict(extra="forbid")

    template: str
    qty: Literal["scalable"] | int = "scalable"
    power_from: list[str] = Field(default_factory=list)


class DeviceTemplate(BaseModel):
    """One device template — leaf (1:1 with equipment_id) or module (aggregation)."""

    model_config = ConfigDict(extra="forbid")

    template: str  # ADR-002 §9 slug
    kind: TemplateKind
    equipment_id: str | None = None
    vendor: str | None = None
    model: str | None = None
    description: str
    contains: list[ContainsEntry] = Field(default_factory=list)
    measurements: dict[str, Measurement] = Field(default_factory=dict)
    commands: dict[str, Command] = Field(default_factory=dict)

    @model_validator(mode="after")
    def slug_format(self) -> "DeviceTemplate":
        """Template name must be a snake_case slug per ADR-002 §9."""
        if not _SLUG_RE.match(self.template):
            raise ValueError(
                f"template slug {self.template!r} must match {_SLUG_RE.pattern}"
            )
        return self

    @model_validator(mode="after")
    def kind_field_consistency(self) -> "DeviceTemplate":
        """Gate all kind-conditional fields: equipment_id, vendor, model, contains."""
        t = self.template
        if self.kind == TemplateKind.LEAF:
            if self.equipment_id is None:
                raise ValueError(f"template {t!r}: equipment_id required for kind=leaf")
            if self.vendor is None:
                raise ValueError(f"template {t!r}: vendor required for kind=leaf")
            if self.model is None:
                raise ValueError(f"template {t!r}: model required for kind=leaf")
            if len(self.contains) > 0:
                raise ValueError(f"template {t!r}: contains forbidden for kind=leaf")
        if self.kind == TemplateKind.MODULE:
            if self.equipment_id is not None:
                raise ValueError(
                    f"template {t!r}: equipment_id forbidden for kind=module"
                )
            if self.vendor is not None:
                raise ValueError(f"template {t!r}: vendor forbidden for kind=module")
            if self.model is not None:
                raise ValueError(f"template {t!r}: model forbidden for kind=module")
        return self

    @model_validator(mode="after")
    def must_have_channels(self) -> "DeviceTemplate":
        """Every template must declare at least one of measurements/commands."""
        if not self.measurements and not self.commands:
            raise ValueError(
                f"template {self.template!r} must declare at least one of "
                "measurements: or commands:"
            )
        return self
