"""Device Topology Manifest — what edp-api emits, what ems-device-api revises.

Canonical shape per ADR-002 §7: parent-chain Devices keyed by snake_case slug,
embedded templates_used map, buses[] with type=dc|ac, three referential-integrity
validators. Primitive types live in dtm_primitives.py (file-size split).
This module re-exports the full public surface so all imports stay stable.
"""

import re
from typing import Final
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from src.shared.schemas.dtm_primitives import (
    PROVISIONED_AT_COMMISSIONING,
    BlockingKind,
    Bus,
    BusMember,
    Connection,
    EmsMode,
    ProvisionedInt,
    SizingParams,
    _contains_sentinel,
)
from src.shared.schemas.template import DeviceTemplate, Measurement

__all__ = [
    "PROVISIONED_AT_COMMISSIONING",
    "BlockingKind",
    "Bus",
    "BusMember",
    "Connection",
    "Device",
    "DeviceTemplate",
    "Dtm",
    "EmsMode",
    "Measurement",
    "ProvisionedInt",
    "SizingParams",
]

_SLUG_RE: Final = re.compile(r"^[a-z][a-z0-9_]{0,62}[a-z0-9]$")


class Device(BaseModel):
    """One device instance — leaf or module per its template's kind."""

    model_config = ConfigDict(extra="forbid")

    device_id: str  # snake_case slug per ADR §9
    template: str  # ref into Dtm.templates_used
    parent: str | None = None  # FK to another Device.device_id
    display_name: str | None = None
    connection: Connection | None = None  # required for gateway-bound leaves
    # Reason: defaults to [LIVE_MODE] — most devices block site live transition
    # until the utility provisions them. Topology authors override to [] for
    # monitoring-only devices, or add COMMISSIONING_COMPLETE for sign-off-blocking.
    blocking: list[BlockingKind] = Field(
        default_factory=lambda: [BlockingKind.LIVE_MODE]
    )
    extra_measurements: dict[str, Measurement] | None = None  # ADR §7 escape hatch

    @field_validator("device_id")
    @classmethod
    def device_id_slug(cls, v: str) -> str:
        """device_id must be a snake_case slug per ADR-002 §9."""
        if not _SLUG_RE.match(v):
            raise ValueError(
                f"device_id {v!r} is not a valid slug — "
                "must match ^[a-z][a-z0-9_]{{0,62}}[a-z0-9]$"
            )
        return v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_placeholders(self) -> bool:
        """True iff any declared field (incl. nested connection) holds the sentinel."""
        return any(
            _contains_sentinel(getattr(self, name)) for name in type(self).model_fields
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mode(self) -> EmsMode:
        """LIVE iff fully provisioned; SIM while any placeholder remains."""
        return EmsMode.SIM if self.has_placeholders else EmsMode.LIVE


class Dtm(BaseModel):
    """Top-level DTM. Mode is derived from Device.has_placeholders, not stored."""

    model_config = ConfigDict(extra="forbid")

    # ems-device-api owns subsequent version bumps (per-device CRUD, template
    # revs, etc.) once the deployment is running and edp-api is no longer in
    # the loop.
    version: str = "1.0.0"
    deployment_uuid: UUID
    sizing_ref: str | None = None
    sizing_params: SizingParams
    devices: dict[str, Device]
    buses: list[Bus]
    templates_used: dict[str, DeviceTemplate]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mode(self) -> EmsMode:
        """LIVE iff every device fully provisioned; SIM if any placeholders."""
        return (
            EmsMode.LIVE
            if all(not d.has_placeholders for d in self.devices.values())
            else EmsMode.SIM
        )

    @model_validator(mode="after")
    def parent_chain_resolves(self) -> "Dtm":
        """Every device.parent must be null or a key in devices."""
        for dev in self.devices.values():
            if dev.parent is not None and dev.parent not in self.devices:
                raise ValueError(
                    f"device {dev.device_id!r}: parent {dev.parent!r} not found in devices"
                )
        return self

    @model_validator(mode="after")
    def template_refs_resolve(self) -> "Dtm":
        """Every device.template must be a key in templates_used."""
        for dev in self.devices.values():
            if dev.template not in self.templates_used:
                raise ValueError(
                    f"device {dev.device_id!r}: template {dev.template!r} "
                    "not found in templates_used"
                )
        return self

    @model_validator(mode="after")
    def bus_members_resolve(self) -> "Dtm":
        """Every bus member device_id must be a key in devices."""
        for bus in self.buses:
            for member in bus.members:
                if member.device_id not in self.devices:
                    raise ValueError(
                        f"bus {bus.bus_id!r}: bus member {member.device_id!r} "
                        "not found in devices"
                    )
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def pending_devices(self) -> list[Device]:
        """Devices still carrying utility-assigned placeholder values."""
        return [d for d in self.devices.values() if d.has_placeholders]
