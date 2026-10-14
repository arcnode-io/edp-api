"""The DTM seen as containers: C1…CN, G1…GM, BESS — each with its devices.

Every run in the schedule names devices by their site tag (C1-PDU-A1), the
same tag the drawings and the BOM use.
"""

import re
from dataclasses import dataclass

from src.dtm.device_roles import BESS_MODULE_TEMPLATES, COMPUTE_MODULE_TEMPLATES
from src.shared.schemas.dtm import Device, Dtm

_NUM = re.compile(r"(\d+)$")


@dataclass(frozen=True)
class Container:
    """One module (compute container, grid container or the battery)."""

    tag: str  # C1, G2, BESS
    kind: str  # "compute", "grid" or "bess"
    devices: list[Device]  # children, in tag order

    def of(self, *templates: str) -> list[Device]:
        """Children using any of these templates, in tag order."""
        return [d for d in self.devices if d.template in templates]

    def one(self, *templates: str) -> Device | None:
        """The first child using any of these templates."""
        found = self.of(*templates)
        return found[0] if found else None


def tag(device: Device) -> str:
    """Site tag, or the device id where the DTM carries none."""
    return device.display_name or device.device_id


def containers(dtm: Dtm) -> list[Container]:
    """Compute, then grid, then battery containers, each in number order."""
    found = []
    for module in dtm.devices.values():
        if module.parent is not None:
            continue
        kind = _kind(module.template)
        if kind is None:
            continue
        children = sorted(
            (d for d in dtm.devices.values() if d.parent == module.device_id),
            key=lambda d: _natural(tag(d)),
        )
        found.append(Container(tag(module), kind, children))
    rank = {"compute": 0, "grid": 1, "bess": 2}
    return sorted(found, key=lambda c: (rank[c.kind], _natural(c.tag)))


def _kind(template: str) -> str | None:
    if template in COMPUTE_MODULE_TEMPLATES:
        return "compute"
    if template in BESS_MODULE_TEMPLATES:
        return "bess"
    return "grid" if template == "grid_module" else None


def _natural(text: str) -> tuple[str, int]:
    """C10 sorts after C9."""
    m = _NUM.search(text)
    return (text[: m.start()], int(m[1])) if m else (text, 0)
