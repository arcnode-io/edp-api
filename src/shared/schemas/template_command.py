"""Template commands — split out of template.py (200-line budget)."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from src.shared.schemas.template_protocols import Binding


class Fanout(StrEnum):
    """Who handles a command that has no direct protocol binding.

    LOCAL_PROCESS: a named local process distributes one logical command
    out to real child devices (e.g. a module-level setpoint fanned out to
    its racks).
    DER_CONTROL_API: a virtual singleton receiver (ems-der-control-api) —
    no children, nothing polled, but same "no binding" shape. Mirrors
    Publisher's identical LOCAL_PROCESS/DER_CONTROL_API pairing for
    measurements (measurement.py).
    """

    LOCAL_PROCESS = "local_process"
    DER_CONTROL_API = "der_control_api"


class Command(BaseModel):
    """One channel a device receives. Either bound to a protocol or
    fanned out by a local process."""

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
