"""Cable + hose schedule output schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class CableEntry(BaseModel):
    """One row in the cables sheet."""

    tag: str  # CBL-0001
    service: str  # "Comms - Modbus TCP" / "Power - 480V 3PH" / ...
    from_device: str  # device_id
    from_port: str  # "TCP/502" or "AWG12/3" or "/dev/ttyUSB0" etc
    to_device: str  # gateway / upstream device
    to_port: str
    cable_type: str  # "Cat6 STP" / "AWG 12/3 SOOW" / "FO LC-LC OM4"
    length_estimate_m: float | None = None
    notes: str = ""


class HoseEntry(BaseModel):
    """One row in the hoses sheet.

    v1 reserves the shape; no hoses are derived from the DTM yet. Hose
    derivation lands when the bus schema grows a `liquid` type or when
    P&ID port resolution surfaces facility-side coolant routing.
    """

    tag: str  # HOS-0001
    service: str  # "Coolant Supply" / "Coolant Return" / "PG/W 25%" / ...
    from_device: str
    from_port: str
    to_device: str
    to_port: str
    hose_type: str  # "EPDM 1in PG/W rated"
    length_estimate_m: float | None = None
    notes: str = ""


class CableHoseSchedule(BaseModel):
    """Top-level schedule output — cables + hoses with deployment metadata."""

    version: Literal["1.0.0"] = "1.0.0"
    deployment_uuid: UUID
    generated_at: datetime
    cables: list[CableEntry] = Field(default_factory=list)
    hoses: list[HoseEntry] = Field(default_factory=list)
