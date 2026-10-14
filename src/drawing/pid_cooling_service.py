"""PidCoolingService — paper-grade cooling P&ID as DXF + PDF.

Two A3 sheets whatever the order size, both drawn for compute container C1
as typical of every compute container:
- Sheet 1: rack (secondary) loop — CDU, supply/return headers, one DLC
  plate per GPU node, ISA 5.1 instruments.
- Sheet 2: facility (primary) loop — CDU, CD plate at the container wall,
  ARCNODE dry cooler, pump and buffer tank by others.
Devices and tags come from the DTM. Every pipe ends on a port, a header,
a symbol or an off-sheet connector.
"""

from pydantic import BaseModel

from src.drawing._drawing_area import bind_to_drawing_area
from src.drawing._eng_render import serialize_dxf, serialize_pdf
from src.drawing._eng_title_block import new_sheet
from src.drawing._pid_facility_sheet import draw_facility_sheet
from src.drawing._pid_kit import LAYERS
from src.drawing._pid_rack_sheet import draw_rack_sheet
from src.shared.schemas.dtm import Dtm


class PidCoolingOutputs(BaseModel):
    """Both rendered formats from one build."""

    model_config = {"arbitrary_types_allowed": True}

    dxf: bytes
    pdf: bytes


class PidCoolingService:
    """Build the cooling P&ID sheets, serialize to DXF + PDF."""

    def generate(self, dtm: Dtm, profile: str = "") -> PidCoolingOutputs:
        """Rack-loop sheet + facility-loop sheet."""
        rack = new_sheet(
            dtm, title="P&ID — RACK COOLANT", profile=profile, layers=LAYERS, n=1, m=2
        )
        facility = new_sheet(
            dtm,
            title="P&ID — FACILITY COOLANT",
            profile=profile,
            layers=LAYERS,
            n=2,
            m=2,
        )
        draw_rack_sheet(rack.modelspace(), rack, dtm)
        draw_facility_sheet(facility.modelspace(), facility, dtm)
        for sheet in (rack, facility):
            bind_to_drawing_area(sheet.modelspace())
        return PidCoolingOutputs(
            dxf=serialize_dxf([rack, facility]),
            pdf=serialize_pdf([rack, facility], title="ARCNODE P&ID — COOLANT SYSTEM"),
        )
