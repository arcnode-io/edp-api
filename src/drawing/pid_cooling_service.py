"""PidCoolingService — paper-grade P&ID for the cooling system as DXF + PDF.

Two sheets:
- Sheet 1 (RACK-INTERNAL): CDU + manifold + per-DLC-plate branches.
  ISA 5.1 instrumentation (TT/PT/FT) on standard port locations.
  Driven from the DTM — one CDU symbol per `cdu` device, one DLC plate
  per `gpu_node` device.
- Sheet 2 (FACILITY LOOP): BY-OTHERS placeholders for the customer-
  supplied dry cooler + facility pump + buffer tank, dashed boundary
  line, and a mirror of the CDU on the right for visual continuity.
  No ConfiguratorPayload data drives sheet 2 today (facility-side gear
  isn't in scope) — the BY-OTHERS placeholders are honest by ISA 5.1
  convention; the customer's facility engineer fills in their actual
  equipment.

DXF carries sheet 1 only (DXF is single-modelspace). The full 2-sheet
deliverable is the PDF artifact.
"""

import ezdxf
from ezdxf.document import Drawing
from ezdxf.layouts import Modelspace
from pydantic import BaseModel

from src.drawing._eng_render import serialize_dxf, serialize_pdf
from src.drawing._eng_title_block import draw_sheet_frame, draw_title_block
from src.drawing._pid_layout import (
    SHEET1_CDU_X,
    SHEET1_CDU_Y,
    SHEET1_MANIFOLD_X,
    SHEET1_MANIFOLD_Y,
    SHEET2_BOUNDARY_X,
    SHEET2_BUFFER_TANK_X,
    SHEET2_BUFFER_TANK_Y,
    SHEET2_CDU_X,
    SHEET2_CDU_Y,
    SHEET2_DRY_COOLER_X,
    SHEET2_DRY_COOLER_Y,
    SHEET2_PUMP_X,
    SHEET2_PUMP_Y,
    stack_dlc_plates,
)
from src.drawing._pid_symbols import (
    ensure_buffer_tank_block,
    ensure_cdu_block,
    ensure_dlc_plate_block,
    ensure_dry_cooler_block,
    ensure_instrument_bubble,
    ensure_manifold_block,
    ensure_pump_block,
)
from src.shared.schemas.dtm import Device, Dtm

# Layer names — kept distinct from the SLD layers for cleaner DXF browsing.
_LAYER_PROCESS: str = "PROCESS"  # pipe lines + equipment outlines
_LAYER_INSTR: str = "INSTRUMENT"  # bubble + signal line
_LAYER_LABELS: str = "LABELS"
_LAYER_BOUNDARY: str = "BOUNDARY"  # BY-OTHERS dashed boundary line


class PidCoolingOutputs(BaseModel):
    """Both rendered formats from one DTM build."""

    model_config = {"arbitrary_types_allowed": True}

    dxf: bytes
    pdf: bytes


class PidCoolingService:
    """Build the cooling P&ID as DXF (sheet 1 only) + PDF (both sheets)."""

    def generate(self, dtm: Dtm, profile: str = "") -> PidCoolingOutputs:
        """Build sheet 1 + sheet 2 docs, return both serialized formats."""
        sheet1 = self._build_sheet1(dtm, profile)
        sheet2 = self._build_sheet2(dtm, profile)
        return PidCoolingOutputs(
            dxf=serialize_dxf(sheet1),
            pdf=serialize_pdf([sheet1, sheet2], title="ARCNODE P&ID — COOLANT SYSTEM"),
        )

    def _build_sheet1(self, dtm: Dtm, profile: str) -> Drawing:
        """Rack-internal cooling: CDU, manifold, per-GPU-node DLC plates."""
        doc = self._new_doc()
        msp = doc.modelspace()
        draw_sheet_frame(msp)
        draw_title_block(
            msp,
            dtm,
            title="P&ID — RACK COOLANT",
            profile=profile,
            sheet_n=1,
            sheet_m=2,
        )

        # CDUs: one symbol per cdu device.
        cdu_block = ensure_cdu_block(doc)
        cdu_devices = _devices_by_template(dtm, "cdu")
        for i, device in enumerate(cdu_devices):
            # Stack multiple CDUs vertically if more than one. Most v1
            # deployments have qty=1 per compute_module — but stacking is
            # cheap insurance and reads honestly when count > 1.
            x = SHEET1_CDU_X
            y = SHEET1_CDU_Y - i * 60
            alias = f"equip_cdu_{device.device_id}"
            _alias_block(doc, alias, cdu_block)
            msp.add_blockref(
                name=alias,
                insert=(x, y),
                dxfattribs={"layer": _LAYER_PROCESS},
            )
            _label_below(msp, x, y - 12, device.device_id)
            _place_cdu_instruments(msp, doc, x, y, tag_prefix=i + 1)

        # Manifold: vertical bar between the CDU and the plate stack.
        manifold_block = ensure_manifold_block(doc)
        msp.add_blockref(
            name=manifold_block,
            insert=(SHEET1_MANIFOLD_X, SHEET1_MANIFOLD_Y),
            dxfattribs={"layer": _LAYER_PROCESS},
        )

        # DLC plates: one per gpu_node device.
        plate_block = ensure_dlc_plate_block(doc)
        gpu_nodes = _devices_by_template(dtm, "gpu_node")
        plate_positions = stack_dlc_plates(len(gpu_nodes))
        for i, (device, placement) in enumerate(
            zip(gpu_nodes, plate_positions, strict=False)
        ):
            alias = f"equip_dlc_{device.device_id}"
            _alias_block(doc, alias, plate_block)
            msp.add_blockref(
                name=alias,
                insert=(placement.insert_x, placement.insert_y),
                dxfattribs={"layer": _LAYER_PROCESS},
            )
            _label_below(
                msp,
                placement.insert_x,
                placement.insert_y - 8,
                device.device_id,
            )
            # TT bubble at the plate return — tag numbers increase
            # top-to-bottom per ISA convention (TT-1001 = topmost rack).
            _insert_instrument(
                msp,
                doc,
                tag=f"TT-{1001 + i:04d}",
                x=placement.insert_x + 22,
                y=placement.insert_y - 3,
            )
            # Process pipe from manifold to plate.
            msp.add_line(
                start=(SHEET1_MANIFOLD_X + 2, placement.insert_y + 3),
                end=(placement.insert_x - 10, placement.insert_y + 3),
                dxfattribs={"layer": _LAYER_PROCESS},
            )
            msp.add_line(
                start=(SHEET1_MANIFOLD_X + 2, placement.insert_y - 3),
                end=(placement.insert_x - 10, placement.insert_y - 3),
                dxfattribs={"layer": _LAYER_PROCESS},
            )

        # CDU secondary supply -> manifold top; CDU secondary return ->
        # manifold bottom. Process pipes at standard line weight.
        if cdu_devices:
            _connect_cdu_to_manifold(msp, SHEET1_CDU_X, SHEET1_CDU_Y)

        return doc

    def _build_sheet2(self, dtm: Dtm, profile: str) -> Drawing:
        """Facility loop: BY-OTHERS dry cooler + pump + tank, CDU mirror, boundary."""
        doc = self._new_doc()
        msp = doc.modelspace()
        draw_sheet_frame(msp)
        draw_title_block(
            msp,
            dtm,
            title="P&ID — FACILITY COOLANT",
            profile=profile,
            sheet_n=2,
            sheet_m=2,
        )

        # Dashed vertical boundary line — BY OTHERS to the left, ARCNODE to the right.
        msp.add_line(
            start=(SHEET2_BOUNDARY_X, 60),
            end=(SHEET2_BOUNDARY_X, 280),
            dxfattribs={"layer": _LAYER_BOUNDARY, "linetype": "DASHED"},
        )
        msp.add_text(
            "ARCNODE SCOPE  >",
            dxfattribs={
                "layer": _LAYER_LABELS,
                "height": 3.0,
                "halign": 0,
                "valign": 2,
                "align_point": (SHEET2_BOUNDARY_X + 3, 280),
            },
        )
        msp.add_text(
            "<  BY OTHERS",
            dxfattribs={
                "layer": _LAYER_LABELS,
                "height": 3.0,
                "halign": 2,  # right
                "valign": 2,
                "align_point": (SHEET2_BOUNDARY_X - 3, 280),
            },
        )

        # BY-OTHERS gear, left side.
        dry_cooler = ensure_dry_cooler_block(doc)
        msp.add_blockref(
            name=dry_cooler,
            insert=(SHEET2_DRY_COOLER_X, SHEET2_DRY_COOLER_Y),
            dxfattribs={"layer": _LAYER_PROCESS},
        )
        pump = ensure_pump_block(doc)
        msp.add_blockref(
            name=pump,
            insert=(SHEET2_PUMP_X, SHEET2_PUMP_Y),
            dxfattribs={"layer": _LAYER_PROCESS},
        )
        _label_below(msp, SHEET2_PUMP_X, SHEET2_PUMP_Y - 10, "FAC PUMP (BY OTHERS)")
        tank = ensure_buffer_tank_block(doc)
        msp.add_blockref(
            name=tank,
            insert=(SHEET2_BUFFER_TANK_X, SHEET2_BUFFER_TANK_Y),
            dxfattribs={"layer": _LAYER_PROCESS},
        )

        # ARCNODE-side CDU mirror, right of the boundary.
        cdu_block = ensure_cdu_block(doc)
        msp.add_blockref(
            name=cdu_block,
            insert=(SHEET2_CDU_X, SHEET2_CDU_Y),
            dxfattribs={"layer": _LAYER_PROCESS},
        )
        _label_below(msp, SHEET2_CDU_X, SHEET2_CDU_Y - 12, "CDU (ARCNODE)")

        # Facility loop pipework — closed loop, supply path + return path.
        # Supply: dry cooler bottom -> pump (vertical down) -> tank (horizontal)
        # -> CDU primary supply (horizontal stub from tank to CDU left-bottom).
        msp.add_line(
            start=(SHEET2_DRY_COOLER_X, SHEET2_DRY_COOLER_Y - 15),
            end=(SHEET2_DRY_COOLER_X, SHEET2_PUMP_Y + 6),
            dxfattribs={"layer": _LAYER_PROCESS},
        )
        msp.add_line(
            start=(SHEET2_PUMP_X + 6, SHEET2_PUMP_Y),
            end=(SHEET2_BUFFER_TANK_X - 15, SHEET2_PUMP_Y),
            dxfattribs={"layer": _LAYER_PROCESS},
        )
        # Tank -> CDU primary supply: 2-segment orthogonal route.
        msp.add_line(
            start=(SHEET2_BUFFER_TANK_X + 15, SHEET2_PUMP_Y),
            end=(SHEET2_CDU_X - 19, SHEET2_PUMP_Y),
            dxfattribs={"layer": _LAYER_PROCESS},
        )
        msp.add_line(
            start=(SHEET2_CDU_X - 19, SHEET2_PUMP_Y),
            end=(SHEET2_CDU_X - 19, SHEET2_CDU_Y - 5),
            dxfattribs={"layer": _LAYER_PROCESS},
        )
        # Return: CDU primary return (horizontal) -> over the boundary line ->
        # tank top -> up the right side of the sheet -> over and into dry
        # cooler top. 4 segments — keep them orthogonal so a reviewer can
        # trace the loop without ambiguity.
        return_y = 260.0  # above all the equipment but below the boundary labels
        msp.add_line(
            start=(SHEET2_CDU_X - 19, SHEET2_CDU_Y + 5),
            end=(SHEET2_CDU_X - 19, return_y),
            dxfattribs={"layer": _LAYER_PROCESS},
        )
        msp.add_line(
            start=(SHEET2_CDU_X - 19, return_y),
            end=(SHEET2_DRY_COOLER_X, return_y),
            dxfattribs={"layer": _LAYER_PROCESS},
        )
        msp.add_line(
            start=(SHEET2_DRY_COOLER_X, return_y),
            end=(SHEET2_DRY_COOLER_X, SHEET2_DRY_COOLER_Y + 15),
            dxfattribs={"layer": _LAYER_PROCESS},
        )

        return doc

    def _new_doc(self) -> Drawing:
        """Fresh ezdxf Drawing with engineering layers + DASHED linetype loaded."""
        doc = ezdxf.new(dxfversion="R2018", setup=True)
        for name in (
            _LAYER_PROCESS,
            _LAYER_INSTR,
            _LAYER_LABELS,
            _LAYER_BOUNDARY,
            "FRAME",
            "TITLE_BLOCK",
        ):
            if name not in doc.layers:
                doc.layers.add(name)
        return doc


def _devices_by_template(dtm: Dtm, template_slug: str) -> list[Device]:
    """Return DTM devices using the given template slug, ordered by device_id."""
    return sorted(
        (d for d in dtm.devices.values() if d.template == template_slug),
        key=lambda d: d.device_id,
    )


def _alias_block(doc: Drawing, alias: str, target: str) -> None:
    """Define an INSERT-able alias whose body is a single INSERT of `target`."""
    if alias in doc.blocks:
        return
    blk = doc.blocks.new(name=alias)
    blk.add_blockref(name=target, insert=(0, 0))


def _label_below(msp: Modelspace, x: float, y: float, text: str) -> None:
    """Center-aligned label below a feature."""
    msp.add_text(
        text,
        dxfattribs={
            "layer": _LAYER_LABELS,
            "height": 2.5,
            "halign": 4,
            "valign": 2,
            "align_point": (x, y),
        },
    )


def _insert_instrument(
    msp: Modelspace,
    doc: Drawing,
    *,
    tag: str,
    x: float,
    y: float,
) -> None:
    """Place an ISA 5.1 instrument bubble at (x,y) with the given tag."""
    blk = ensure_instrument_bubble(doc, tag)
    msp.add_blockref(name=blk, insert=(x, y), dxfattribs={"layer": _LAYER_INSTR})


def _place_cdu_instruments(
    msp: Modelspace,
    doc: Drawing,
    cdu_x: float,
    cdu_y: float,
    *,
    tag_prefix: int,
) -> None:
    """TT + PT on each of the 4 CDU ports, FT on the secondary supply.

    Total 9 bubbles per CDU. Tag numbering: 100*tag_prefix + offset so
    multiple CDUs on one sheet don't clash.
    """
    base = 100 * tag_prefix
    # PRI supply (left top): TT/PT
    _insert_instrument(msp, doc, tag=f"TT-{base + 1:04d}", x=cdu_x - 25, y=cdu_y + 12)
    _insert_instrument(msp, doc, tag=f"PT-{base + 2:04d}", x=cdu_x - 25, y=cdu_y + 2)
    # PRI return (left bottom): TT/PT
    _insert_instrument(msp, doc, tag=f"TT-{base + 3:04d}", x=cdu_x - 25, y=cdu_y - 12)
    _insert_instrument(msp, doc, tag=f"PT-{base + 4:04d}", x=cdu_x - 25, y=cdu_y - 22)
    # SEC supply (right top): TT/PT + FT
    _insert_instrument(msp, doc, tag=f"TT-{base + 5:04d}", x=cdu_x + 25, y=cdu_y + 12)
    _insert_instrument(msp, doc, tag=f"PT-{base + 6:04d}", x=cdu_x + 25, y=cdu_y + 2)
    _insert_instrument(msp, doc, tag=f"FT-{base + 7:04d}", x=cdu_x + 35, y=cdu_y + 6)
    # SEC return (right bottom): TT/PT
    _insert_instrument(msp, doc, tag=f"TT-{base + 8:04d}", x=cdu_x + 25, y=cdu_y - 12)
    _insert_instrument(msp, doc, tag=f"PT-{base + 9:04d}", x=cdu_x + 25, y=cdu_y - 22)


def _connect_cdu_to_manifold(msp: Modelspace, cdu_x: float, cdu_y: float) -> None:
    """Two process pipes from CDU secondary to manifold supply/return tees."""
    msp.add_line(
        start=(cdu_x + 19, cdu_y + 5),
        end=(SHEET1_MANIFOLD_X - 2, cdu_y + 5),
        dxfattribs={"layer": _LAYER_PROCESS},
    )
    msp.add_line(
        start=(cdu_x + 19, cdu_y - 5),
        end=(SHEET1_MANIFOLD_X - 2, cdu_y - 5),
        dxfattribs={"layer": _LAYER_PROCESS},
    )
