"""Device Topology Manifest — what edp-api emits, what ems-device-api revises.

Top-level schema; protocol-level types live in dtm_protocols.py.
This module re-exports the protocol surface so existing imports keep working.
"""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, computed_field, model_validator

from src.shared.schemas.dtm_protocols import (
    PROVISIONED_AT_COMMISSIONING,
    CanopenGwConfig,
    Dnp3TcpConfig,
    ModbusTcpConfig,
    OidMap,
    PdoMap,
    PointMap,
    ProtocolConfig,
    ProtocolKind,
    ProvisionedInt,
    RedfishConfig,
    RedfishResourceMap,
    SnmpConfig,
    SnmpV3Creds,
)

__all__ = [
    "PROVISIONED_AT_COMMISSIONING",
    "BlockingKind",
    "CanopenGwConfig",
    "Device",
    "Dnp3TcpConfig",
    "Dtm",
    "EmsMode",
    "ModbusTcpConfig",
    "Module",
    "OidMap",
    "PdoMap",
    "PointMap",
    "ProtocolConfig",
    "ProtocolKind",
    "ProvisionedInt",
    "RedfishConfig",
    "RedfishResourceMap",
    "SizingParams",
    "SnmpConfig",
    "SnmpV3Creds",
]


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

    P_compute_total_kW: float
    E_BESS_total_kWh: float
    T_coolant_setpoint_C: float


class Module(BaseModel):
    """One container instance."""

    module_id: str
    module_type: str
    container_position: str
    description: str


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


class Device(BaseModel):
    """One physical device inside a Module."""

    device_uuid: UUID
    device_type: str
    module_id: str  # FK -> Module.module_id
    host: str
    port: ProvisionedInt
    protocol_config: ProtocolConfig
    description: str
    # Reason: defaults to [LIVE_MODE] — most devices block site live transition
    # until the utility provisions them. Topology authors override to [] for
    # monitoring-only devices, or add COMMISSIONING_COMPLETE for sign-off-blocking.
    blocking: list[BlockingKind] = Field(
        default_factory=lambda: [BlockingKind.LIVE_MODE]
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_placeholders(self) -> bool:
        """True iff any declared field (incl. nested protocol_config) holds the sentinel."""
        return any(
            _contains_sentinel(getattr(self, name)) for name in type(self).model_fields
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mode(self) -> EmsMode:
        """LIVE iff fully provisioned; SIM while any placeholder remains."""
        return EmsMode.SIM if self.has_placeholders else EmsMode.LIVE


class Dtm(BaseModel):
    """Top-level DTM. SIM at edp-api emit; ems-device-api flips to LIVE."""

    deployment_uuid: UUID
    ems_mode: EmsMode = EmsMode.SIM
    sizing_params: SizingParams
    modules: list[Module]
    devices: list[Device]

    @model_validator(mode="after")
    def fk_modules(self) -> "Dtm":
        """Every Device.module_id must reference an existing Module.module_id."""
        ids = {m.module_id for m in self.modules}
        for d in self.devices:
            if d.module_id not in ids:
                raise ValueError(
                    f"device {d.device_uuid}: module_id {d.module_id!r} not in modules"
                )
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def pending_devices(self) -> list[Device]:
        """Devices still carrying utility-assigned placeholder values."""
        return [d for d in self.devices if d.has_placeholders]
