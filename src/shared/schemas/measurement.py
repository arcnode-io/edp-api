"""Measurement schema — one channel a device emits.

Measurements are either protocol-bound (gateway polls the binding) or
publisher-driven (line-controller/analyst computes a rollup). Optional Bounds
and Thresholds describe physical range + alarm bands; both forbidden for
type=enum and must satisfy the cross-field "alarms inside bounds" rule.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from src.shared.schemas.measurement_ranges import (
    Bounds,
    Thresholds,
    check_thresholds_inside_bounds,
)
from src.shared.schemas.template_protocols import Binding


class Publisher(StrEnum):
    """Who publishes a measurement that has no protocol binding (rollups)."""

    LINE_CONTROLLER = "line_controller"
    ANALYST = "analyst"


class Measurement(BaseModel):
    """One channel a device emits. Either bound to a protocol or
    published by line-controller/analyst."""

    model_config = ConfigDict(extra="forbid")

    unit: str  # ADR-002 §3 enum-locked vocabulary
    type: Literal["float", "bool", "enum"]
    poll_rate_hz: float | None = None
    display_name_default: str | None = None
    iec_61850_ref: str | None = None
    values: dict[int, str] | None = None
    bounds: Bounds | None = None
    thresholds: Thresholds | None = None
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

    @model_validator(mode="after")
    def _ranges_constraints(self) -> "Measurement":
        """bounds/thresholds forbidden for enum; thresholds must lie inside bounds."""
        if self.type == "enum" and (
            self.bounds is not None or self.thresholds is not None
        ):
            raise ValueError("bounds/thresholds forbidden for type=enum")
        check_thresholds_inside_bounds(self.bounds, self.thresholds)
        return self
