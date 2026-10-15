"""SldEngineeringService — paper-grade single-line diagram as DXF + PDF.

The engineering deliverable an electrical engineer reviews and signs:
the power path from utility to loads. Two A3 sheets whatever the order
size — site one-line (sheet 1) and one compute container drawn as
typical (sheet 2). Equipment comes from the BOM; anything the BOM
doesn't carry is labelled PART TBD in the equipment list.

Not the HMI SLD: that one draws every EMS device from the DTM at runtime.
"""

from pydantic import BaseModel

from src.bom_generator.bom_models import Bom
from src.drawing._draw_kit import LAYERS
from src.drawing._drawing_area import bind_to_drawing_area
from src.drawing._eng_render import serialize_dxf, serialize_pdf
from src.drawing._eng_title_block import new_sheet
from src.drawing._sld_compute_sheet import draw_compute_sheet
from src.drawing._sld_site_sheet import draw_site_sheet
from src.shared.schemas.dtm import Dtm


class SldEngineeringOutputs(BaseModel):
    """Both rendered formats from one build."""

    model_config = {"arbitrary_types_allowed": True}

    dxf: bytes
    pdf: bytes


class SldEngineeringService:
    """Build the SLD sheets, serialize to DXF + PDF."""

    def generate(self, dtm: Dtm, *, bom: Bom, profile: str) -> SldEngineeringOutputs:
        """Site sheet + typical compute sheet. dtm only feeds the title block."""
        sheets = [
            new_sheet(
                dtm, title="SLD — SITE", profile=profile, layers=LAYERS, n=1, m=2
            ),
            new_sheet(
                dtm,
                title="SLD — COMPUTE CONTAINER",
                profile=profile,
                layers=LAYERS,
                n=2,
                m=2,
            ),
        ]
        draw_site_sheet(sheets[0].modelspace(), bom)
        draw_compute_sheet(sheets[1].modelspace(), bom)
        for sheet in sheets:
            bind_to_drawing_area(sheet.modelspace())
        return SldEngineeringOutputs(
            dxf=serialize_dxf(sheets),
            pdf=serialize_pdf(sheets, title="ARCNODE SLD"),
        )
