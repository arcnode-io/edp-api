"""Per-assembly device topology yaml shape.

Authored in `edp-module-assemblies/assemblies/<type>/<variant>/topology.yaml`,
fetched by URL from `manifest.yaml`. Per ADR-002 §7 + §14: device_template
references resolve against edp-api/device_templates/ at DTM emit time.
"""

from typing import Literal

from pydantic import BaseModel, Field

from src.shared.schemas.dtm import BlockingKind, ProvisionedInt


class TopologyConnectionSpec(BaseModel):
    """Per-instance runtime connection params authored alongside the device."""

    host: str
    port: ProvisionedInt
    unit_id: str | None = None    # modbus unit_id, dnp3 outstation, etc.


class TopologyDeviceSpec(BaseModel):
    """One device entry inside an assembly's topology yaml."""

    template: str                  # references a slug in edp-api/device_templates/
    description: str
    connection: TopologyConnectionSpec
    blocking: list[BlockingKind] = Field(
        default_factory=lambda: [BlockingKind.LIVE_MODE]
    )


class TopologyBusMemberSpec(BaseModel):
    """One member declaration in a bus — pattern over device_template."""

    device_template: str          # generator expands per resolution count
    port: str | None = None       # references a port_id on the device's equipment


class TopologyBusSpec(BaseModel):
    """Electrical bus connecting devices via their ports."""

    bus_id: str
    type: Literal["dc", "ac"]
    members: list[TopologyBusMemberSpec]


class TopologyYaml(BaseModel):
    """Top-level topology yaml: devices + buses authored per assembly variant."""

    devices: list[TopologyDeviceSpec]
    buses: list[TopologyBusSpec] = Field(default_factory=list)
