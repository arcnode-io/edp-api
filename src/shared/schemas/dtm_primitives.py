"""Primitive DTM types — sentinel, ProvisionedInt, enums, and simple models.

Split from dtm.py to keep both files under the 200-line budget.
Consumers import from src.shared.schemas.dtm (re-exported there).
"""

from enum import StrEnum
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

# Sentinel used in DTM YAML for fields the utility assigns at commissioning.
# Presence of this value in any field flags a Device as still pending.
# Reason: typed as Final without explicit annotation so the type is the
# Literal string, not str — lets ProvisionedInt accept it cleanly.
PROVISIONED_AT_COMMISSIONING: Final = "PROVISIONED_AT_COMMISSIONING"

# Int field that may carry the placeholder until the utility provisions it.
ProvisionedInt = int | Literal["PROVISIONED_AT_COMMISSIONING"]


class EmsMode(StrEnum):
    """EMS execution mode. SIM on initial emit; ems-device-api flips to LIVE."""

    SIM = "sim"
    LIVE = "live"


class BlockingKind(StrEnum):
    """What unresolved placeholders on a device block.

    LIVE_MODE: device must be fully provisioned before site flips to live.
    COMMISSIONING_COMPLETE: device must be provisioned for site sign-off.
    """

    LIVE_MODE = "live_mode"
    COMMISSIONING_COMPLETE = "commissioning_complete"


class SizingParams(BaseModel):
    """Aggregate sizing for the deployment — drives EMS bookkeeping."""

    model_config = ConfigDict(extra="forbid")

    P_compute_total_kW: float
    E_BESS_total_kWh: float
    T_coolant_setpoint_C: float


class Connection(BaseModel):
    """Per-device runtime connection params."""

    model_config = ConfigDict(extra="forbid")

    host: str  # may be PROVISIONED_AT_COMMISSIONING
    port: ProvisionedInt  # int | sentinel
    unit_id: str | None = None  # modbus unit_id, dnp3 outstation, etc.


class BusMember(BaseModel):
    """One device reference in a bus members list."""

    model_config = ConfigDict(extra="forbid")

    device_id: str
    port: str | None = None


class Bus(BaseModel):
    """Electrical bus connecting devices via their ports."""

    model_config = ConfigDict(extra="forbid")

    bus_id: str
    type: Literal["dc", "ac"]
    members: list[BusMember]


def _contains_sentinel(value: object) -> bool:
    """Recursively scan declared model fields for the placeholder sentinel."""
    if isinstance(value, str):
        return value == PROVISIONED_AT_COMMISSIONING
    if isinstance(value, BaseModel):
        return any(
            _contains_sentinel(getattr(value, name))
            for name in type(value).model_fields
        )
    if isinstance(value, list):
        return any(_contains_sentinel(v) for v in value)
    return False
