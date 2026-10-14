"""CommsDiagramService — paper-grade management-network diagram as DXF + PDF.

Two A3 sheets whatever the order size: the site network (sheet 1) and one
compute container drawn as typical (sheet 2). Devices, protocols and
addresses come from the DTM; container counts and parts from the BOM.
"""

from pydantic import BaseModel

from src.bom_generator.bom_models import Bom
from src.drawing._comms_compute_sheet import draw_compute_sheet
from src.drawing._comms_site_sheet import draw_site_sheet
from src.drawing._draw_kit import LAYERS
from src.drawing._drawing_area import bind_to_drawing_area
from src.drawing._eng_render import serialize_dxf, serialize_pdf
from src.drawing._eng_title_block import new_sheet
from src.shared.schemas.dtm import Dtm


class CommsDiagramOutputs(BaseModel):
    """Both rendered formats from one build."""

    model_config = {"arbitrary_types_allowed": True}

    dxf: bytes
    pdf: bytes


class CommsDiagramService:
    """Build the comms sheets, serialize to DXF + PDF."""

    def generate(self, dtm: Dtm, *, bom: Bom, profile: str) -> CommsDiagramOutputs:
        """Site sheet + typical compute sheet."""
        sheets = [
            new_sheet(
                dtm, title="COMMS — SITE", profile=profile, layers=LAYERS, n=1, m=2
            ),
            new_sheet(
                dtm,
                title="COMMS — COMPUTE CONTAINER",
                profile=profile,
                layers=LAYERS,
                n=2,
                m=2,
            ),
        ]
        draw_site_sheet(sheets[0].modelspace(), dtm, bom)
        draw_compute_sheet(sheets[1].modelspace(), dtm, bom)
        for sheet in sheets:
            bind_to_drawing_area(sheet.modelspace())
        return CommsDiagramOutputs(
            dxf=serialize_dxf(sheets),
            pdf=serialize_pdf(sheets, title="ARCNODE COMMS DIAGRAM"),
        )
