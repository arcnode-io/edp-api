"""CommsDiagramService — paper-grade communications topology DXF + PDF.

Logical-topology view: devices grouped by protocol family (Modbus TCP,
DNP3 TCP, SNMP, Redfish, CANopen-GW). Each cluster has a gateway hub on
the left and devices fanning out to the right, with per-device
`host:port` (+ optional unit_id) surfaced under each box.

Driven entirely from the DTM:
- Each Device.connection gives host + port (+ optional unit_id).
- The device's first measurement's `binding.protocol` discriminator
  decides which cluster the device joins. Devices whose template has no
  bound measurements fall into a SYNTHETIC / UNBOUND cluster.

Single sheet. v1 doesn't paginate (clusters wrap to a second sub-row
inside their pitch when they exceed `DEVICES_PER_ROW`).
"""

import ezdxf
from ezdxf.document import Drawing
from ezdxf.layouts import Modelspace
from pydantic import BaseModel

from src.drawing._comms_layout import (
    ClusterPlacement,
    DeviceSlot,
    layout_clusters,
)
from src.drawing._comms_symbols import (
    ensure_device_box_block,
    ensure_gateway_glyph_block,
)
from src.drawing._eng_render import serialize_dxf, serialize_pdf
from src.drawing._eng_title_block import draw_sheet_frame, draw_title_block
from src.shared.schemas.dtm import Device, Dtm
from src.shared.schemas.template import DeviceTemplate

# Protocol-discriminator (Binding.protocol literal) → cluster label shown on the
# sheet. Order is sheet-vertical order (Modbus first / top, etc).
_PROTOCOL_LABELS: dict[str, str] = {
    "modbus_tcp": "MODBUS TCP",
    "dnp3_tcp": "DNP3 TCP",
    "snmp": "SNMP",
    "redfish": "REDFISH",
    "canopen_gw": "CANOPEN GW",
    "synthetic": "SYNTHETIC / DERIVED",
}
_UNBOUND_LABEL: str = "UNBOUND / NO BINDING"

_LAYER_NODES: str = "NODES"
_LAYER_LINKS: str = "LINKS"
_LAYER_LABELS: str = "LABELS"


class CommsDiagramOutputs(BaseModel):
    """Both rendered formats from one DTM build."""

    model_config = {"arbitrary_types_allowed": True}

    dxf: bytes
    pdf: bytes


class CommsDiagramService:
    """Build the comms diagram as DXF + PDF."""

    def generate(self, dtm: Dtm, profile: str = "") -> CommsDiagramOutputs:
        """Build sheet, return both serialized formats."""
        doc = self._build_drawing(dtm, profile)
        return CommsDiagramOutputs(
            dxf=serialize_dxf(doc),
            pdf=serialize_pdf([doc], title="ARCNODE COMMS DIAGRAM"),
        )

    def _build_drawing(self, dtm: Dtm, profile: str) -> Drawing:
        doc = self._new_doc()
        msp = doc.modelspace()
        draw_sheet_frame(msp)
        draw_title_block(
            msp,
            dtm,
            title="COMMS DIAGRAM",
            profile=profile,
            sheet_n=1,
            sheet_m=1,
        )

        devices_by_protocol = _group_devices_by_protocol(dtm)
        clusters = layout_clusters(devices_by_protocol)

        device_block = ensure_device_box_block(doc)
        gateway_block = ensure_gateway_glyph_block(doc)

        for cluster in clusters:
            _draw_cluster_header(msp, cluster)
            _draw_gateway(msp, cluster, gateway_block)
            for slot in cluster.devices:
                _draw_device(
                    msp,
                    doc,
                    dtm,
                    slot,
                    device_block_name=device_block,
                )
                _draw_link(msp, cluster, slot)

        return doc

    def _new_doc(self) -> Drawing:
        doc = ezdxf.new(dxfversion="R2018", setup=True)
        for name in (
            _LAYER_NODES,
            _LAYER_LINKS,
            _LAYER_LABELS,
            "FRAME",
            "TITLE_BLOCK",
        ):
            if name not in doc.layers:
                doc.layers.add(name)
        return doc


def _group_devices_by_protocol(dtm: Dtm) -> dict[str, list[str]]:
    """Map cluster label -> list of device_ids, preserving _PROTOCOL_LABELS order.

    A device's cluster is decided by the protocol on the FIRST measurement
    of its template. Templates with no bound measurements (commands-only,
    or fanout-only) drop into the UNBOUND cluster.
    """
    result: dict[str, list[str]] = {label: [] for label in _PROTOCOL_LABELS.values()}
    result[_UNBOUND_LABEL] = []
    for did in sorted(dtm.devices):
        device = dtm.devices[did]
        template = dtm.templates_used.get(device.template)
        cluster_label = _cluster_label_for_template(template)
        result[cluster_label].append(did)
    # Drop empty clusters so they don't waste vertical space on the sheet.
    return {label: ids for label, ids in result.items() if ids}


def _cluster_label_for_template(template: DeviceTemplate | None) -> str:
    """Pick the cluster label for a device based on its template's first binding."""
    if template is None or not template.measurements:
        return _UNBOUND_LABEL
    for measurement in template.measurements.values():
        if measurement.binding is None:
            continue
        proto = getattr(measurement.binding, "protocol", None)
        if proto in _PROTOCOL_LABELS:
            return _PROTOCOL_LABELS[proto]
    return _UNBOUND_LABEL


def _draw_cluster_header(msp: Modelspace, cluster: ClusterPlacement) -> None:
    """MTEXT above the gateway showing the protocol label."""
    msp.add_mtext(
        cluster.protocol_label,
        dxfattribs={
            "layer": _LAYER_LABELS,
            "char_height": 3.5,
            "insert": (cluster.header_x, cluster.header_y),
            "attachment_point": 4,  # middle-left
            "width": 380.0,
        },
    )


def _draw_gateway(
    msp: Modelspace,
    cluster: ClusterPlacement,
    gateway_block_name: str,
) -> None:
    """INSERT the gateway glyph at the cluster's gateway position."""
    msp.add_blockref(
        name=gateway_block_name,
        insert=(cluster.gateway_x, cluster.gateway_y),
        dxfattribs={"layer": _LAYER_NODES},
    )


def _draw_device(
    msp: Modelspace,
    doc: Drawing,
    dtm: Dtm,
    slot: DeviceSlot,
    *,
    device_block_name: str,
) -> None:
    """INSERT a device-box alias + 2 text labels (device_id + host:port)."""
    alias = f"device_{slot.device_id}"
    if alias not in doc.blocks:
        alias_blk = doc.blocks.new(name=alias)
        alias_blk.add_blockref(name=device_block_name, insert=(0, 0))
    msp.add_blockref(
        name=alias,
        insert=(slot.x, slot.y),
        dxfattribs={"layer": _LAYER_NODES},
    )

    device = dtm.devices[slot.device_id]
    # device_id (top label) — 2.5mm text centered above the box body.
    msp.add_text(
        slot.device_id,
        dxfattribs={
            "layer": _LAYER_LABELS,
            "height": 2.5,
            "halign": 4,
            "valign": 2,
            "align_point": (slot.x, slot.y + 3),
        },
    )
    # host:port (bottom label) — 2.0mm text inside the box body.
    if device.connection is not None:
        unit_suffix = ""
        if device.connection.unit_id:
            unit_suffix = f"  u={device.connection.unit_id}"
        msp.add_text(
            f"{device.connection.host}:{device.connection.port}{unit_suffix}",
            dxfattribs={
                "layer": _LAYER_LABELS,
                "height": 2.0,
                "halign": 4,
                "valign": 2,
                "align_point": (slot.x, slot.y - 3),
            },
        )


def _draw_link(msp: Modelspace, cluster: ClusterPlacement, slot: DeviceSlot) -> None:
    """LINE from gateway right edge to device box left edge.

    Orthogonal 3-segment route when the device is on a sub-row that
    doesn't share the gateway's y — keeps connections readable at a
    glance instead of a long diagonal across the page.
    """
    gw_right_x = cluster.gateway_x + 12  # gateway block half-width
    dev_left_x = slot.x - 20  # device box half-width
    if abs(slot.y - cluster.gateway_y) < 1e-3:
        # Same row — single horizontal segment.
        msp.add_line(
            start=(gw_right_x, cluster.gateway_y),
            end=(dev_left_x, slot.y),
            dxfattribs={"layer": _LAYER_LINKS},
        )
        return
    # Sub-row — vertical drop midway, then horizontal to the device.
    mid_x = gw_right_x + 8
    msp.add_line(
        start=(gw_right_x, cluster.gateway_y),
        end=(mid_x, cluster.gateway_y),
        dxfattribs={"layer": _LAYER_LINKS},
    )
    msp.add_line(
        start=(mid_x, cluster.gateway_y),
        end=(mid_x, slot.y),
        dxfattribs={"layer": _LAYER_LINKS},
    )
    msp.add_line(
        start=(mid_x, slot.y),
        end=(dev_left_x, slot.y),
        dxfattribs={"layer": _LAYER_LINKS},
    )


# Re-export for convenience.
__all__ = ["CommsDiagramOutputs", "CommsDiagramService"]


def _devices_by_template(dtm: Dtm, template_slug: str) -> list[Device]:
    """Unused helper kept for parity with sibling generators."""
    return sorted(
        (d for d in dtm.devices.values() if d.template == template_slug),
        key=lambda d: d.device_id,
    )
