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
"""

import graphviz

from src.drawing._layout import layout_devices
from src.drawing._svg import author_svg
from src.shared.schemas.dtm import Dtm


class SldHmiSvgService:
    """Generates the runtime SLD SVG artifact (`sld_hmi.svg`) from a DTM."""

    def generate(self, dtm: Dtm) -> bytes:
        """Render the structural SVG for HMI runtime overlay + animation.

        Args:
            dtm: The deployment's Device Topology Manifest.

        Returns:
            UTF-8 encoded SVG bytes — deterministic per DTM input.
        """
        graph = graphviz.Digraph(engine="dot")
        for device_id in dtm.devices:
            graph.node(device_id)
        plain = graph.pipe(format="plain").decode()
        positions = layout_devices(plain)
        return author_svg(dtm, positions).encode("utf-8")
