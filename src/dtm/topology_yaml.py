"""Per-assembly device topology yaml shape.

Lives in `edp-module-assemblies` repo; fetched by URL from `hardware_selector_map.yaml`.
"""

from pydantic import BaseModel, Field

from src.shared.schemas.dtm import BlockingKind, ProtocolConfig, ProvisionedInt


class TopologyDeviceSpec(BaseModel):
    """One device entry inside an assembly's topology yaml."""

    device_type: str
    description: str
    host: str
    port: ProvisionedInt
    protocol_config: ProtocolConfig
    # Reason: defaults to [LIVE_MODE] — assembly authors override only when a
    # device is monitoring-only or also blocks commissioning sign-off.
    blocking: list[BlockingKind] = Field(
        default_factory=lambda: [BlockingKind.LIVE_MODE]
    )


class TopologyYaml(BaseModel):
    """Top-level topology yaml: list of devices that ship inside one assembly."""

    devices: list[TopologyDeviceSpec]
