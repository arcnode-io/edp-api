"""CableHoseScheduleService — every cable and hose run, derived from the DTM.

The schedule is the drawings, run by run, named by the same site tags:
- Power (_power_cables): the single-line diagram — container feeders,
  panelboard branches, A/B node feeds.
- Comms (_comms_cables): the comms diagram — device patches to each
  container's management switch, fiber uplinks to G1, G1 to the EMS host.
- Hoses (_hoses): the P&ID — primary loop to the dry cooler, secondary
  loop to each node's DLC plate.
JSON (canonical) + XLSX outputs. Lengths are field-measured.
"""

from datetime import UTC, datetime
from io import BytesIO
from typing import Final

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from src.cable_hose_schedule._comms_cables import comms_cables
from src.cable_hose_schedule._hoses import hoses
from src.cable_hose_schedule._power_cables import power_cables
from src.cable_hose_schedule._site_index import containers
from src.cable_hose_schedule.cable_hose_schedule_models import (
    CableEntry,
    CableHoseSchedule,
    HoseEntry,
)
from src.shared.schemas.dtm import Dtm

_COLUMNS: Final[tuple[tuple[str, str, int], ...]] = (
    ("tag", "Tag", 10),
    ("service", "Service", 40),
    ("from_device", "From", 16),
    ("from_port", "From port", 12),
    ("to_device", "To", 16),
    ("to_port", "To port", 12),
    ("kind", "Cable / hose type", 50),
    ("length_estimate_m", "Length (m)", 14),
    ("notes", "Notes", 50),
)


class CableHoseScheduleService:
    """Derives the cable + hose schedule from the DTM."""

    def generate(self, dtm: Dtm) -> CableHoseSchedule:
        """Power then comms cables (CBL-0001…), hoses (HOS-0001…)."""
        sites = containers(dtm)
        cables = power_cables(sites) + comms_cables(dtm, sites)
        found = hoses(sites)
        return CableHoseSchedule(
            deployment_uuid=dtm.deployment_uuid,
            generated_at=datetime.now(UTC),
            cables=[
                c.model_copy(update={"tag": f"CBL-{i:04d}"})
                for i, c in enumerate(cables, 1)
            ],
            hoses=[
                h.model_copy(update={"tag": f"HOS-{i:04d}"})
                for i, h in enumerate(found, 1)
            ],
        )


def serialize_cable_hose_schedule_xlsx(schedule: CableHoseSchedule) -> bytes:
    """Two sheets — Cables and Hoses — every cell filled."""
    wb = Workbook()
    cables_ws = wb.active
    assert cables_ws is not None
    cables_ws.title = "Cables"
    _write(cables_ws, schedule.cables)
    _write(wb.create_sheet(title="Hoses"), schedule.hoses)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _write(ws: Worksheet, rows: list[CableEntry] | list[HoseEntry]) -> None:
    ws.append([label for _, label, _ in _COLUMNS])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for i, (_, _, width) in enumerate(_COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "A2"
    for entry in rows:
        kind = entry.cable_type if isinstance(entry, CableEntry) else entry.hose_type
        length = entry.length_estimate_m
        ws.append(
            [
                entry.tag,
                entry.service,
                entry.from_device,
                entry.from_port,
                entry.to_device,
                entry.to_port,
                kind,
                "Field-measured" if length is None else length,
                entry.notes or "—",
            ]
        )
