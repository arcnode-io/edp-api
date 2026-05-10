"""Device template schema — canonical vocabulary per ADR-002 §7.

Templates own per-measurement protocol bindings (Modbus FC, DNP3 addrs,
SNMP OIDs). DTMs reference templates by slug; per-instance Devices contribute
deployment specifics (host, port, parent, display_name).
Protocol-level binding types live in template_protocols.py.
This module re-exports the protocol surface so existing imports keep working.
"""

import re
from enum import StrEnum
from typing import Final, Literal

from pydantic import BaseModel, Field, model_validator

from src.shared.schemas.template_protocols import (
    Binding,
    CanopenBinding,
    Dnp3Binding,
    ModbusBinding,
    RedfishBinding,
    SnmpBinding,
)

__all__ = [
    "Binding",
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
    "TemplateKind",
]

_SLUG_RE: Final = re.compile(r"^[a-z][a-z0-9_]{0,62}[a-z0-9]$")


class TemplateKind(StrEnum):
    """Leaf templates have equipment_id; modules are aggregations with contains."""

    LEAF = "leaf"
    MODULE = "module"


class Publisher(StrEnum):
    """Who publishes a measurement that has no protocol binding (rollups)."""

    LINE_CONTROLLER = "line_controller"
    ANALYST = "analyst"


class Fanout(StrEnum):
    """Who handles a command that has no direct binding (fans out to children)."""

    LINE_CONTROLLER = "line_controller"


class Measurement(BaseModel):
    """One channel a device emits. Either bound to a protocol or
    published by line-controller/analyst."""

    unit: str  # ADR-002 §3 enum-locked vocabulary
    type: Literal["float", "bool", "enum"]
    poll_rate_hz: float | None = None
    display_name_default: str | None = None
    iec_61850_ref: str | None = None
    values: dict[int, str] | None = None
    binding: Binding | None = None
    publisher: Publisher | None = None

    @model_validator(mode="after")
    def _values_enum_constraint(self) -> "Measurement":
        """values required iff type=enum."""
        if self.type == "enum" and self.values is None:
            raise ValueError("type=enum requires values")
        if self.type != "enum" and self.values is not None:
            raise ValueError("values forbidden for non-enum type")
        return self

    @model_validator(mode="after")
    def _binding_xor_publisher(self) -> "Measurement":
        """Each measurement MUST have exactly one of binding or publisher."""
        has_binding = self.binding is not None
        has_publisher = self.publisher is not None
        if has_binding == has_publisher:
            raise ValueError(
                "measurement requires exactly one of `binding:` (gateway-bound) "
                "or `publisher:` (derived/rollup)"
            )
        return self


class Command(BaseModel):
    """One channel a device receives. Either bound to a protocol or
    fanned out by line-controller."""

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
    """Reference to a child template inside a module's contains[]."""

    template: str
    qty: Literal["scalable"] | int = "scalable"


class DeviceTemplate(BaseModel):
    """One device template — leaf (1:1 with equipment_id) or module (aggregation)."""

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
