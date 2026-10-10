"""Roll the cable + hose schedule up into BOM lines (one per cable/hose type)."""

from collections import Counter

from src.bom_generator.bom_models import BomLineItem, ProcurementPath
from src.cable_hose_schedule.cable_hose_schedule_models import CableHoseSchedule


def cable_hose_lines(schedule: CableHoseSchedule) -> list[BomLineItem]:
    """One catalog line per cable/hose type; qty = run count (lengths are field-measured)."""
    runs = Counter(c.cable_type for c in schedule.cables)
    runs.update(h.hose_type for h in schedule.hoses)
    return [
        BomLineItem(
            part_number=kind,
            vendor="TBD",
            description=f"{kind}, {qty} runs, lengths field-measured",
            qty=qty,
            procurement_path=ProcurementPath.CATALOG,
        )
        for kind, qty in runs.items()
    ]
