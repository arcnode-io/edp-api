"""Bom → xlsx: the BOM sheet the customer reads, and a purchase roll-up.

BOM sheet: title, an order block (as placed and as delivered), then the
lines grouped by section with a subtotal each, a grand total and a
legend. Every line cell is filled (bom_cells). Totals are budgetary
(bom_pricing): the customer buys every part and runs their own RFQs.
Purchase roll-up (bom_rollup_xlsx): one row per part, summed.
"""

from io import BytesIO
from typing import Final

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from src.bom_generator.bom_cells import COLUMNS, row
from src.bom_generator.bom_models import Bom, BomBudget, BomSection
from src.bom_generator.bom_pricing import PURCHASED, order_budget
from src.bom_generator.bom_rollup_xlsx import rollup_sheet
from src.module_resolver.deployment_profile import GPUS_PER_NODE

_GPU: Final[dict[str, str]] = {"h100_sxm": "H100 SXM", "b200": "B200"}
_COUPLING: Final[dict[str, str]] = {
    "ac_coupled": "AC-coupled",
    "dc_integrated_pcs": "DC with its own PCS",
    "dc_external_pcs": "DC to a PCS on the battery pad",
}
_BOLD: Final[Font] = Font(bold=True)
_HEAD_FILL: Final[PatternFill] = PatternFill("solid", fgColor="D9D9D9")
_SECTION_FILL: Final[PatternFill] = PatternFill("solid", fgColor="EDEDED")
_WRAP: Final[Alignment] = Alignment(wrap_text=True, vertical="top")
_MONEY: Final[str] = "$#,##0.00"
_UNIT_COL, _EXT_COL, _BASIS_COL = 11, 12, 13  # 1-based, per bom_cells.COLUMNS
_NOTES_COL: Final[int] = len(COLUMNS)


def serialize_bom_xlsx(bom: Bom) -> bytes:
    """Serialize a Bom to xlsx bytes for S3 upload."""
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "BOM"
    _bom_sheet(ws, bom)
    rollup_sheet(wb.create_sheet("Purchase roll-up"), bom)
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

    _sections(ws, bom)
    _total_row(ws, "BUDGET TOTAL (budgetary)", order_budget(bom.line_items))
    ws.append([])
    for note in _LEGEND:
        ws.append([note])


def _sections(ws: Worksheet, bom: Bom) -> None:
    """Section title, lines and budget subtotal per section."""
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
        if any(li.procurement_path in PURCHASED for li in lines):
            _total_row(ws, "Subtotal (budgetary)", order_budget(lines))
        else:
            ws.append([None, "Nothing to buy in this section"])


def _order_block(bom: Bom) -> list[tuple[str, str]]:
    o = bom.order
    n, m = bom.compute_container_qty, bom.grid_container_qty
    gpu = _GPU.get(o.gpu_variant, o.gpu_variant)
    servers = o.gpus_delivered // GPUS_PER_NODE
    return [
        ("Customer", o.customer),
        ("Site", o.site),
        ("Deployment", str(bom.deployment_id)),
        ("Profile", f"{bom.profile} ({o.deployment_context})"),
        (
            "Compute",
            f"{o.gpus_requested} x {gpu} requested → {servers} server"
            f"{'s' if servers != 1 else ''} ({o.gpus_delivered} GPUs) in {n} "
            f"compute container{'s' if n != 1 else ''}",
        ),
        ("Grid", f"{m} grid container{'s' if m != 1 else ''}, 1000 kVA Trihal each"),
        (
            "Battery",
            f"{o.bess_capacity_mwh:g} MWh, {_COUPLING.get(o.bess_coupling, o.bess_coupling)},"
            " customer-supplied",
        ),
        ("Budget", _budget_text(order_budget(bom.line_items))),
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


def _budget_text(b: BomBudget) -> str:
    """One line: total, range, how much is quote-backed, what's missing."""
    unpriced = f"; {b.unpriced_lines} line(s) unpriced" if b.unpriced_lines else ""
    return (
        f"${b.total_usd:,.0f} budgetary, range ${b.low_usd:,.0f} to ${b.high_usd:,.0f}; "
        f"{b.quote_backed_pct:.0f}% from vendor quotes{unpriced}"
    )


def _total_row(ws: Worksheet, label: str, b: BomBudget) -> None:
    cells: list = [None] * len(COLUMNS)
    cells[1], cells[_EXT_COL - 1] = label, b.total_usd
    cells[_BASIS_COL - 1] = f"Range ${b.low_usd:,.0f} to ${b.high_usd:,.0f}"
    cells[_NOTES_COL - 1] = (
        f"{b.unpriced_lines} line(s) unpriced, not in total"
        if b.unpriced_lines
        else "All lines priced"
    )
    ws.append(cells)
    ws.cell(ws.max_row, 2).font = _BOLD
    ws.cell(ws.max_row, _EXT_COL).number_format = _MONEY


_LEGEND: Final[tuple[str, ...]] = (
    "Prices are budgetary, not quotes: each line's price basis gives its "
    "source, date and ± band (quote ±10%, distributor ±15%, estimate ±40%).",
    "RFQ: lead time comes from your request for quote.",
    "Supplied by: Customer buys it or already owns it; By others = the "
    "customer's site contractors; Installer supplies bulk field material.",
    "Ref des: device tags, the same ones used on the drawings and in the device data.",
)
