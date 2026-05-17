"""SldHmiSvgService — emits the HMI runtime SLD SVG per DTM.

The HMI overlays live MQTT values on positioned SVG element IDs and animates
particles along bus paths. This generator is structural-only: device-node
groups with `id={device_id}`, bus paths with `id=bus_{bus_id}`, and
`data-region` subelements that HMI selectors hook into. No inline colors,
no embedded measurement values, no SIM watermark.

Bus path direction rule: path start = source-side device. When the source-side
device's MMXU.W is positive (export/discharge), particles flow start → end.
HMI handles forward/reverse animation via animateMotion from/to regardless of
path drawing direction; the contract is the rule, not the geometry.

Orientation: `landscape` (default) yields graphviz's single-row dot layout —
no edges, devices spread on the x-axis. `portrait` adds invisible bus-member
edges + rankdir=TB so dot stacks bus members vertically. The HMI picks per
viewport shape (phone → portrait, desktop → landscape).
"""

from itertools import pairwise
from typing import Literal

import graphviz

from src.drawing._layout import layout_devices
from src.drawing._svg import author_svg
from src.shared.schemas.dtm import Dtm

Orientation = Literal["landscape", "portrait"]


class SldHmiSvgService:
    """Generates the runtime SLD SVG artifact (`sld_hmi.svg`) from a DTM."""

    def generate(self, dtm: Dtm, orientation: Orientation = "landscape") -> bytes:
        """Render the structural SVG for HMI runtime overlay + animation.

        Args:
            dtm: The deployment's Device Topology Manifest.
            orientation: `landscape` (default, horizontal row) or
                `portrait` (vertical stack via TB rankdir + bus edges).

        Returns:
            UTF-8 encoded SVG bytes — deterministic per (DTM, orientation).
        """
        graph = graphviz.Digraph(engine="dot")
        if orientation == "portrait":
            # Reason: TB rankdir + invisible bus-member edges force graphviz
            # to assign separate ranks (y-coords) to bus members. Without
            # edges dot would still emit a single row.
            graph.attr(rankdir="TB")
        for device_id in dtm.devices:
            graph.node(device_id)
        if orientation == "portrait":
            for bus in dtm.buses:
                ids = [m.device_id for m in bus.members]
                for parent, child in pairwise(ids):
                    graph.edge(parent, child, style="invis")
        plain = graph.pipe(format="plain").decode()
        positions = layout_devices(plain)
        return author_svg(dtm, positions).encode("utf-8")
