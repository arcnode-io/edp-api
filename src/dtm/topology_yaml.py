"""Per-assembly device topology yaml shape.

Lives in `edp-module-assemblies` repo; fetched by URL from `hardware_selector_map.yaml`.
"""

from pydantic import BaseModel

from src.shared.schemas.dtm import ProtocolConfig


class TopologyDeviceSpec(BaseModel):
    """One device entry inside an assembly's topology yaml."""

    device_type: str
    description: str
    host: str
    port: int
    protocol_config: ProtocolConfig


class TopologyYaml(BaseModel):
    """Top-level topology yaml: list of devices that ship inside one assembly."""

    devices: list[TopologyDeviceSpec]
