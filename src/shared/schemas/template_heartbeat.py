"""Keep-alive a device needs from the EMS, declared on its template.

The gateway writes a counter (0, 1, … counter_modulo-1, 0, …) to `binding`
every `period_s`, only while its broker link is up and the device isn't
locked out; if the EMS goes away the beat stops and the device's own
watchdog fails safe.
"""

from pydantic import BaseModel, ConfigDict, Field

from src.shared.schemas.template_protocols import ModbusBinding


class Heartbeat(BaseModel):
    """Counter the EMS writes on a fixed period so the device knows it's alive."""

    model_config = ConfigDict(extra="forbid")

    binding: ModbusBinding  # where the counter goes (a write function code)
    counter_modulo: int = Field(gt=1)
    period_s: float = Field(gt=0)
