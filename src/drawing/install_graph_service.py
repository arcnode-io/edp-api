"""InstallGraphService — schematic per-container floor plan DXF + PDF.

One sheet per module device in the deployment (compute_module,
grid_module, bess_module). Each sheet shows:
- ISO-container outline (10ft high-cube; floor plan footprint).
- Each child device as a labeled equipment box.
- Service-clearance halo (dashed) around each device.
- Title block flagged "SCHEMATIC — NOT TO SCALE".

v1 placement is logical / schematic, NOT to real container scale.
Precise equipment positions land in v2 when `edp-module-assemblies`
surfaces a `layout.json` artifact alongside each assembly's
`topology.yaml`. The schematic shape is still useful as a
"what equipment lives in this container" floor-plan reference for
site installers, and clearly marked so they don't read it as a
to-scale drawing.

DXF carries sheet 1 only (DXF is single-modelspace). The full
multi-sheet deliverable is the PDF artifact.
"""

import ezdxf
from ezdxf.document import Drawing
from ezdxf.layouts import Modelspace
from pydantic import BaseModel

from src.drawing._eng_render import serialize_dxf, serialize_pdf
from src.drawing._eng_title_block import draw_sheet_frame, draw_title_block
from src.drawing._install_graph_layout import (
    CONTAINER_HEIGHT,
    CONTAINER_WIDTH,
    CONTAINER_X,
    CONTAINER_Y,
    stack_devices_along_wall,
)
from src.drawing._install_graph_symbols import (
    ensure_clearance_halo_block,
    ensure_equipment_box_block,
)
from src.shared.schemas.dtm import Device, Dtm
from src.shared.schemas.template import TemplateKind

_LAYER_CONTAINER: str = "CONTAINER"
_LAYER_EQUIPMENT: str = "EQUIPMENT"
_LAYER_CLEARANCE: str = "CLEARANCE"
_LAYER_LABELS: str = "LABELS"


class InstallGraphOutputs(BaseModel):
    """Both rendered formats from one DTM build."""

    model_config = {"arbitrary_types_allowed": True}

    dxf: bytes
    pdf: bytes


class InstallGraphService:
    """Builds the schematic install graph as DXF (sheet 1) + PDF (all sheets)."""

    def generate(self, dtm: Dtm, profile: str = "") -> InstallGraphOutputs:
        """Build one Drawing per module device in the DTM."""
        modules = _module_devices(dtm)
        if not modules:
            # No module devices — emit a single empty sheet so the artifact
            # is still well-formed. Real deployments always have ≥1 module.
            modules = [None]
        pages: list[Drawing] = []
        for i, module in enumerate(modules, start=1):
            pages.append(
                self._build_module_sheet(
                    dtm, module, profile, sheet_n=i, sheet_m=len(modules)
                )
            )
        return InstallGraphOutputs(
            dxf=serialize_dxf(pages[0]),
            pdf=serialize_pdf(pages, title="ARCNODE INSTALLATION GRAPH"),
        )

    def _build_module_sheet(
        self,
        dtm: Dtm,
        module: Device | None,
        profile: str,
        *,
        sheet_n: int,
        sheet_m: int,
    ) -> Drawing:
        doc = self._new_doc()
        msp = doc.modelspace()
        draw_sheet_frame(msp)

        module_slug = module.template if module is not None else "EMPTY"
        title = f"INSTALLATION GRAPH — {module_slug.upper()} (SCHEMATIC — NOT TO SCALE)"
        draw_title_block(
            msp,
            dtm,
            title=title,
            profile=profile,
            sheet_n=sheet_n,
            sheet_m=sheet_m,
        )

        # Container outline.
        _draw_container_outline(msp)

        if module is None:
            return doc

        # Equipment + clearance halos for each child device of the module.
        child_ids = sorted(
            did for did, d in dtm.devices.items() if d.parent == module.device_id
        )
        placements = stack_devices_along_wall(child_ids)

        eq_block = ensure_equipment_box_block(doc)
        halo_block = ensure_clearance_halo_block(doc)
        for placement in placements:
            # Service-clearance halo BEHIND the equipment box so the box
            # outline reads cleanly on top.
            msp.add_blockref(
                name=halo_block,
                insert=(placement.x, placement.y),
                dxfattribs={"layer": _LAYER_CLEARANCE},
            )
            # Per-instance alias so tests can query `device_<id>` by INSERT name.
            alias = f"device_{placement.device_id}"
            _alias_block(doc, alias, eq_block)
            msp.add_blockref(
                name=alias,
                insert=(placement.x, placement.y),
                dxfattribs={"layer": _LAYER_EQUIPMENT},
            )
            # device_id label centered in the equipment box.
            msp.add_text(
                placement.device_id,
                dxfattribs={
                    "layer": _LAYER_LABELS,
                    "height": 2.5,
                    "halign": 4,
                    "valign": 2,
                    "align_point": (placement.x, placement.y),
                },
            )

        return doc

    def _new_doc(self) -> Drawing:
        doc = ezdxf.new(dxfversion="R2018", setup=True)
        for name in (
            _LAYER_CONTAINER,
            _LAYER_EQUIPMENT,
            _LAYER_CLEARANCE,
            _LAYER_LABELS,
            "FRAME",
            "TITLE_BLOCK",
        ):
            if name not in doc.layers:
                doc.layers.add(name)
        return doc


def _module_devices(dtm: Dtm) -> list[Device]:
    """Sorted module devices in the DTM (compute_module, grid_module, bess_module)."""
    modules: list[Device] = []
    for did in sorted(dtm.devices):
        device = dtm.devices[did]
        template = dtm.templates_used.get(device.template)
        if template is not None and template.kind == TemplateKind.MODULE:
            modules.append(device)
    return modules


def _draw_container_outline(msp: Modelspace) -> None:
    """10ft high-cube ISO floor plan — schematic rectangle on CONTAINER layer."""
    x, y, w, h = CONTAINER_X, CONTAINER_Y, CONTAINER_WIDTH, CONTAINER_HEIGHT
    msp.add_lwpolyline(
        [(x, y), (x + w, y), (x + w, y + h), (x, y + h)],
        close=True,
        dxfattribs={"layer": _LAYER_CONTAINER},
    )
    # Container floor-plan dimension label (schematic ref to ADR-004 real size).
    msp.add_text(
        "10ft ISO high-cube interior  (real: 2680x2235x2591 mm)",
        dxfattribs={
            "layer": _LAYER_LABELS,
            "height": 2.2,
            "halign": 0,
            "valign": 2,
            "align_point": (x + 3, y - 5),
        },
    )


def _alias_block(doc: Drawing, alias: str, target: str) -> None:
    """Per-device-id alias block whose body INSERTs the shared equipment block."""
    if alias in doc.blocks:
        return
    blk = doc.blocks.new(name=alias)
    blk.add_blockref(name=target, insert=(0, 0))
