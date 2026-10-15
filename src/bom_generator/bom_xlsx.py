"""Bom → xlsx: the BOM sheet the customer reads, and a purchase roll-up.

BOM sheet: title, an order block (as placed and as delivered), then the
lines grouped by section with a subtotal each, a grand total and a
legend. Every line cell is filled (bom_cells). Purchase roll-up: one row
per part ARCNODE buys, quantities summed across sections.
"""

from io import BytesIO
from typing import Final

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from src.bom_generator.bom_cells import COLUMNS, row, unit_cost
from src.bom_generator.bom_models import Bom, BomLineItem, BomSection
from src.module_resolver.deployment_profile import GPUS_PER_COMPUTE_CONTAINER

_GPU: Final[dict[str, str]] = {"h100_sxm": "H100 SXM", "b200": "B200"}
_COUPLING: Final[dict[str, str]] = {
    "ac_coupled": "AC-coupled",
    "dc_integrated_pcs": "DC with its own PCS",
    "dc_external_pcs": "DC to the ARCNODE PCS",
}
_BOLD: Final[Font] = Font(bold=True)
_HEAD_FILL: Final[PatternFill] = PatternFill("solid", fgColor="D9D9D9")
_SECTION_FILL: Final[PatternFill] = PatternFill("solid", fgColor="EDEDED")
_WRAP: Final[Alignment] = Alignment(wrap_text=True, vertical="top")
_MONEY: Final[str] = "$#,##0.00"
_UNIT_COL, _EXT_COL, _NOTES_COL = 11, 12, 17  # 1-based, per bom_cells.COLUMNS


def serialize_bom_xlsx(bom: Bom) -> bytes:
    """Serialize a Bom to xlsx bytes for S3 upload."""
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "BOM"
    _bom_sheet(ws, bom)
    _rollup_sheet(wb.create_sheet("Purchase roll-up"), bom)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _bom_sheet(ws: Worksheet, bom: Bom) -> None:
    ws.append(["ARCNODE — BILL OF MATERIALS"])
    ws["A1"].font = Font(bold=True, size=14)
    for key, value in _order_block(bom):
        ws.append([key, value])
        ws.cell(ws.max_row, 1).font = _BOLD
    ws.append([])
    ws.append([h for h, _ in COLUMNS])
    for cell in ws[ws.max_row]:
        cell.font, cell.fill = _BOLD, _HEAD_FILL
    ws.freeze_panes = ws.cell(ws.max_row + 1, 1)
    for i, (_, width) in enumerate(COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width

    total = _sections(ws, bom)
    _total_row(ws, "TOTAL, priced lines", total, _priced(bom.line_items)[1])
    ws.append([])
    for note in _LEGEND:
        ws.append([note])


def _sections(ws: Worksheet, bom: Bom) -> float:
    """Section title, lines and subtotal per section; returns the priced total."""
    total = 0.0
    for section in BomSection:
        lines = [li for li in bom.line_items if li.section == section]
        if not lines:
            continue
        ws.append([_section_title(section, bom)])
        for cell in ws[ws.max_row]:
            cell.font, cell.fill = _BOLD, _SECTION_FILL
        for line in lines:
            ws.append(row(line))
            for cell in ws[ws.max_row]:
                cell.alignment = _WRAP
            for col in (_UNIT_COL, _EXT_COL):
                ws.cell(ws.max_row, col).number_format = _MONEY
        if any(li.supplied_by == "ARCNODE" for li in lines):
            subtotal, rfq = _priced(lines)
            total += subtotal
            _total_row(ws, "Subtotal, priced lines", subtotal, rfq)
        else:
            ws.append([None, "No ARCNODE-supplied lines in this section"])
    return total


def _order_block(bom: Bom) -> list[tuple[str, str]]:
    o = bom.order
    n, m = bom.compute_container_qty, bom.grid_container_qty
    gpu = _GPU.get(o.gpu_variant, o.gpu_variant)
    return [
        ("Customer", o.customer),
        ("Site", o.site),
        ("Deployment", str(bom.deployment_id)),
        ("Profile", f"{bom.profile} ({o.deployment_context})"),
        (
            "Compute",
            f"{o.gpus_requested} x {gpu} requested → {n} compute container"
            f"{'s' if n != 1 else ''}, {o.gpus_delivered} GPUs "
            f"(whole containers of {GPUS_PER_COMPUTE_CONTAINER})",
        ),
        ("Grid", f"{m} grid container{'s' if m != 1 else ''}, 1000 kVA Trihal each"),
        (
            "Battery",
            f"{o.bess_capacity_mwh:g} MWh, {_COUPLING.get(o.bess_coupling, o.bess_coupling)},"
            " customer-supplied",
        ),
        (
            "Revision",
            f"A · manifest {bom.manifest_version} · {bom.generated_at:%Y-%m-%d}",
        ),
    ]


def _section_title(section: BomSection, bom: Bom) -> str:
    n, m = bom.compute_container_qty, bom.grid_container_qty
    return {
        BomSection.COMPUTE: f"COMPUTE CONTAINERS — C1{f'-C{n}' if n > 1 else ''} (x{n})",
        BomSection.GRID: f"GRID CONTAINERS — G1{f'-G{m}' if m > 1 else ''} (x{m})",
        BomSection.SITE: "SITE AND INTERFACES",
        BomSection.FIELD: "FIELD INSTALL MATERIAL",
    }[section]


def _priced(lines: list[BomLineItem]) -> tuple[float, int]:
    """(sum of priced ARCNODE lines, count of ARCNODE lines still at RFQ)."""
    ours = [li for li in lines if li.supplied_by == "ARCNODE"]
    priced = [(unit_cost(li), li.qty) for li in ours]
    return (
        sum(u * q for u, q in priced if u is not None),
        sum(1 for u, _ in priced if u is None),
    )


def _total_row(ws: Worksheet, label: str, amount: float, rfq: int) -> None:
    cells: list = [None] * len(COLUMNS)
    cells[1], cells[_EXT_COL - 1] = label, amount
    cells[_NOTES_COL - 1] = (
        f"{rfq} line(s) at RFQ, not in total" if rfq else "All lines priced"
    )
    ws.append(cells)
    ws.cell(ws.max_row, 2).font = _BOLD
    ws.cell(ws.max_row, _EXT_COL).number_format = _MONEY


_LEGEND: Final[tuple[str, ...]] = (
    "RFQ: price or lead time comes from the request for quote.",
    "Supplied by: ARCNODE buys it; Customer brings it; By others = the "
    "customer's site contractors; Installer supplies bulk field material.",
    "Ref des: device tags, the same ones used on the drawings and in the device data.",
)


def _rollup_sheet(ws: Worksheet, bom: Bom) -> None:
    headers = [
        "Manufacturer",
        "Part number",
        "Qty",
        "UoM",
        "Description",
        "Sections",
        "Unit cost (USD)",
        "Ext. cost (USD)",
        "Lead time (wk)",
    ]
    ws.append(headers)
    for cell in ws[1]:
        cell.font, cell.fill = _BOLD, _HEAD_FILL
    # Reason: key on equipment_id too, so two engineered-to-order parts that
    # share a vendor placeholder stay separate rows.
    parts: dict[tuple[str, str, str | None], list[BomLineItem]] = {}
    for li in bom.line_items:
        if li.supplied_by == "ARCNODE":
            parts.setdefault((li.vendor, li.part_number, li.equipment_id), []).append(
                li
            )
    for (vendor, part, _), lines in parts.items():
        qty = sum(li.qty for li in lines)
        unit = unit_cost(lines[0])
        lead = lines[0].lead_time_weeks
        ws.append(
            [
                vendor,
                part,
                qty,
                lines[0].uom,
                lines[0].description,
                ", ".join(sorted({li.section.value for li in lines})),
                "RFQ" if unit is None else unit,
                "RFQ" if unit is None else unit * qty,
                "RFQ" if lead is None else lead,
            ]
        )
    for i, width in enumerate((24, 30, 6, 6, 60, 30, 14, 14, 10), start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
