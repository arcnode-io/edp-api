"""What each BOM column shows for a line — every cell has a value.

A sourced value wins. Where none exists the cell says why: "RFQ" (price
or lead time comes from the request for quote), the supplier for lines
ARCNODE doesn't buy ("Customer", "By others", "Installer"), or "N/A"
where a column doesn't apply. Notes default to traceability: the
equipment spec a catalog line comes from, a plate's material and finish.
"""

from typing import Final

from src.bom_generator.bom_models import BomLineItem, ProcurementPath

Cell = str | int | float

# (header, width) in sheet order
COLUMNS: Final[tuple[tuple[str, int], ...]] = (
    ("Item", 6),
    ("Ref des", 30),
    ("Qty", 6),
    ("UoM", 6),
    ("Manufacturer", 24),
    ("Part number", 30),
    ("Description", 60),
    ("Supplied by", 12),
    ("Procurement", 20),
    ("Lead time (wk)", 10),
    ("Unit cost (USD)", 14),
    ("Ext. cost (USD)", 14),
    ("Datasheet / drawing", 40),
    ("Fab tier", 16),
    ("NDAA 889", 10),
    ("TAA", 12),
    ("Notes", 50),
)

_PATH_LABEL: Final[dict[ProcurementPath, str]] = {
    ProcurementPath.CATALOG: "Catalog",
    ProcurementPath.ENGINEERED_TO_ORDER: "Engineered to order",
    ProcurementPath.CUSTOM_FABRICATION: "Custom fabrication",
    ProcurementPath.CUSTOMER_SUPPLIED: "Customer supplied",
    ProcurementPath.BY_OTHERS: "By others",
    ProcurementPath.FIELD_SUPPLIED: "Field supplied",
}
_SET_AT_RFQ: Final[str] = "Set at RFQ"


def row(line: BomLineItem) -> list[Cell]:
    """One sheet row for a line, in COLUMNS order, no empty cells."""
    unit = unit_cost(line)
    return [
        line.item,
        line.ref_des,
        line.qty,
        line.uom,
        line.vendor,
        line.part_number,
        line.description,
        line.supplied_by,
        _PATH_LABEL[line.procurement_path],
        _or_status(line, line.lead_time_weeks),
        _or_status(line, unit),
        _or_status(line, None if unit is None else unit * line.qty),
        _document(line),
        _compliance(line, line.fab_tier),
        _compliance(line, _yes_no(line.ndaa_compliant, "No")),
        _compliance(line, _yes_no(line.taa_compliant, "Not verified")),
        _notes(line),
    ]


def unit_cost(line: BomLineItem) -> float | None:
    """Cheapest live distributor price, else the spec's unit cost."""
    priced = [
        o.unit_cost_usd for o in line.offers if o.error is None and o.unit_cost_usd
    ]
    return min(priced) if priced else line.unit_cost_usd


def _arcnode(line: BomLineItem) -> bool:
    return line.supplied_by == "ARCNODE"


def _or_status(line: BomLineItem, value: float | int | None) -> Cell:
    if value is not None:
        return value
    return "RFQ" if _arcnode(line) else line.supplied_by


def _document(line: BomLineItem) -> str:
    if line.datasheet_url or line.drawing_url:
        return line.datasheet_url or line.drawing_url or ""
    if not _arcnode(line):
        return "N/A"
    if line.equipment_id:
        return f"Requirement spec {line.equipment_id}"
    return "ARCNODE build spec (ADR-004)"


def _compliance(line: BomLineItem, value: str | None) -> str:
    if not _arcnode(line):
        return "N/A"
    return value if value is not None else _SET_AT_RFQ


def _yes_no(value: bool | None, no: str) -> str | None:
    return None if value is None else ("Yes" if value else no)


def _notes(line: BomLineItem) -> str:
    parts = [line.notes] if line.notes else []
    if line.equipment_id:
        parts.append(f"Equipment spec {line.equipment_id}.")
    if line.material:
        parts.append(
            f"{line.material}, {line.finish}." if line.finish else f"{line.material}."
        )
    if not parts:
        parts.append("ARCNODE design, fabricated to order.")
    return " ".join(parts)
