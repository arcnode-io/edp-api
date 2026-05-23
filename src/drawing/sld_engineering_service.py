"""SldEngineeringService — paper-grade SLD as DXF + PDF.

Different artifact from the SLD HMI SVG: this is the engineering
deliverable that an electrical engineer reviews / signs / hands to a
contractor. Symbols are IEC 60617 primitives, sheet is A3 landscape with
an ISO 5457 frame + an ISO 7200-lite title block in the bottom-right
corner.

Backward-compat contract with the HMI SVG: both renderings consume the
same DTM and must agree on the device set and on per-bus source-side
identification. Shared introspection lives in `_iec_61850.py` so the
classification rule can't drift between the two outputs.
"""

import io

import ezdxf
import matplotlib

# Reason: pick a non-interactive backend before importing pyplot so the
# matplotlib agg path doesn't try to attach to a display (Docker / CI).
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.config import (
    BackgroundPolicy,
    ColorPolicy,
    Configuration,
)
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
from ezdxf.document import Drawing
from ezdxf.layouts import Modelspace
from matplotlib.backends.backend_pdf import PdfPages
from pydantic import BaseModel

from src.drawing._eng_title_block import draw_sheet_frame, draw_title_block
from src.drawing._sld_eng_layout import DevicePlacement, layout_devices
from src.drawing._sld_eng_symbols import ensure_symbol_block
from src.shared.schemas.dtm import Bus, Dtm

# A3 landscape in inches: 420 mm x 297 mm / 25.4 mm/in
_A3_LANDSCAPE_INCHES: tuple[float, float] = (16.54, 11.69)
_PDF_DPI: int = 300

# Layer names — keep the engineering review categories clean + scriptable.
_LAYER_DEVICES: str = "DEVICES"
_LAYER_BUS: str = "BUS"
_LAYER_LABELS: str = "LABELS"


class SldEngineeringOutputs(BaseModel):
    """Both rendered formats from one DTM build."""

    model_config = {"arbitrary_types_allowed": True}

    dxf: bytes
    pdf: bytes


class SldEngineeringService:
    """Build the SLD ezdxf Drawing once, serialize to DXF + PDF."""

    def generate(self, dtm: Dtm, profile: str = "") -> SldEngineeringOutputs:
        """Build + serialize. Profile is a label-only field on the title block."""
        doc = self._build_drawing(dtm, profile)
        return SldEngineeringOutputs(dxf=_serialize_dxf(doc), pdf=_serialize_pdf(doc))

    def _build_drawing(self, dtm: Dtm, profile: str) -> Drawing:
        """Compose title block + per-device symbols + bus lines into a Drawing."""
        doc = ezdxf.new(dxfversion="R2018", setup=True)
        _ensure_layers(doc)
        msp = doc.modelspace()

        # Sheet frame + title block first (background).
        draw_sheet_frame(msp)
        draw_title_block(msp, dtm, title="SINGLE LINE DIAGRAM", profile=profile)

        # Lay out devices, define a symbol block per template, INSERT one
        # block reference per device. Block name `device_{device_id}` is a
        # second-level alias so tests + downstream tools can find the per-
        # instance INSERT by device_id (not just by template).
        placements = layout_devices(dtm)
        for device_id, placement in placements.items():
            device = dtm.devices[device_id]
            template = dtm.templates_used[device.template]
            symbol_block_name = ensure_symbol_block(doc, template)
            device_block_name = f"device_{device_id}"
            _ensure_device_alias(doc, device_block_name, symbol_block_name)
            msp.add_blockref(
                name=device_block_name,
                insert=(placement.x, placement.y),
                dxfattribs={"layer": _LAYER_DEVICES},
            )
            # Equipment ID label below each symbol — reviewer can match the
            # drawing to the BOM / spec without chasing back to the DTM.
            _label_device(msp, placement, template_equipment_id=template.equipment_id)

        # Bus geometry on a dedicated layer (LINE per adjacent pair of members).
        for bus in dtm.buses:
            _draw_bus(msp, bus, placements)

        return doc


def _ensure_layers(doc: Drawing) -> None:
    """Idempotent layer creation — engineering review expects these names."""
    layers = doc.layers
    for name in (_LAYER_DEVICES, _LAYER_BUS, _LAYER_LABELS, "FRAME", "TITLE_BLOCK"):
        if name not in layers:
            layers.add(name)


def _ensure_device_alias(doc: Drawing, alias: str, target: str) -> None:
    """Make `device_<id>` an INSERT-able alias that draws the symbol block.

    A block whose body is a single INSERT of another block. Tests + tools
    can query INSERT entities by device-specific names while we still
    share the IEC 60617 geometry via the per-template symbol block.
    """
    if alias in doc.blocks:
        return
    alias_block = doc.blocks.new(name=alias)
    alias_block.add_blockref(name=target, insert=(0, 0))


def _label_device(
    msp: Modelspace,
    placement: DevicePlacement,
    template_equipment_id: str | None,
) -> None:
    """Text label under each symbol: device_id (top) + equipment_id (bottom)."""
    msp.add_text(
        placement.device_id,
        dxfattribs={
            "layer": _LAYER_LABELS,
            "height": 2.5,
            "halign": 4,  # center
            "valign": 2,
            "align_point": (placement.x, placement.y - 10),
        },
    )
    if template_equipment_id:
        msp.add_text(
            template_equipment_id,
            dxfattribs={
                "layer": _LAYER_LABELS,
                "height": 2.0,
                "halign": 4,
                "valign": 2,
                "align_point": (placement.x, placement.y - 13),
            },
        )


def _draw_bus(
    msp: Modelspace,
    bus: Bus,
    placements: dict[str, DevicePlacement],
) -> None:
    """One LINE per pair of adjacent members. Bus ID labelled at the left end."""
    members = [m.device_id for m in bus.members if m.device_id in placements]
    if len(members) < 2:
        return
    pts = [placements[m] for m in members]
    # Horizontal connector through device centers at their row's y.
    y = pts[0].y - 6  # 6 mm below symbol center
    x_left = min(p.x for p in pts)
    x_right = max(p.x for p in pts)
    msp.add_line(start=(x_left, y), end=(x_right, y), dxfattribs={"layer": _LAYER_BUS})
    # Stub from each symbol down to the bus line.
    for p in pts:
        msp.add_line(start=(p.x, p.y), end=(p.x, y), dxfattribs={"layer": _LAYER_BUS})
    # Bus label to the right of the rightmost stub.
    msp.add_text(
        bus.bus_id,
        dxfattribs={
            "layer": _LAYER_LABELS,
            "height": 2.5,
            "halign": 0,
            "valign": 2,
            "align_point": (x_right + 3, y),
        },
    )


def _serialize_dxf(doc: Drawing) -> bytes:
    """ASCII DXF bytes. ezdxf.write takes a text stream."""
    buf = io.StringIO()
    doc.write(buf, fmt="asc")
    return buf.getvalue().encode("utf-8")


def _serialize_pdf(doc: Drawing) -> bytes:
    """A3-landscape PDF rendered via ezdxf.addons.drawing.matplotlib.

    Black-on-white render: ezdxf default leaves layer-7 entities at color 7
    which matplotlib then draws white. PDF viewers with white backgrounds
    show a blank page. Configuration forces black foreground + white
    background so the engineering deliverable is reviewer-readable.
    """
    cfg = Configuration(
        background_policy=BackgroundPolicy.WHITE,
        color_policy=ColorPolicy.BLACK,
    )
    pdf_buf = io.BytesIO()
    with PdfPages(pdf_buf, metadata={"Title": "ARCNODE SLD"}) as pdf:
        fig = plt.figure(figsize=_A3_LANDSCAPE_INCHES)
        # Reason: matplotlib's stubs expect a 4-tuple, not a list.
        ax = fig.add_axes((0.0, 0.0, 1.0, 1.0))
        ax.set_axis_off()
        ctx = RenderContext(doc)
        Frontend(ctx, MatplotlibBackend(ax), config=cfg).draw_layout(
            doc.modelspace(), finalize=True
        )
        pdf.savefig(fig, dpi=_PDF_DPI, facecolor="white")
        plt.close(fig)
    return pdf_buf.getvalue()
