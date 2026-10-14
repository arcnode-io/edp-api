"""Roll the cable + hose schedule up into BOM lines (one per cable/hose type)."""

from src.bom_generator.bom_models import BomLineItem, BomSection, ProcurementPath
from src.bom_generator.bom_ref_des import compress
from src.cable_hose_schedule.cable_hose_schedule_models import CableHoseSchedule


def cable_hose_lines(schedule: CableHoseSchedule) -> list[BomLineItem]:
    """One field-install line per cable/hose type; qty = runs.

    Bulk material the installer supplies and cuts to the field-measured
    lengths; the line's reference designators are the schedule's run tags.
    """
    runs: dict[str, list[str]] = {}
    for cable in schedule.cables:
        runs.setdefault(cable.cable_type, []).append(cable.tag)
    for hose in schedule.hoses:
        runs.setdefault(hose.hose_type, []).append(hose.tag)
    return [
        BomLineItem(
            section=BomSection.FIELD,
            ref_des=compress(tags),
            part_number=kind,
            vendor="Installer",
            description=f"{kind}, cut to field-measured length per run",
            qty=len(tags),
            uom="run",
            procurement_path=ProcurementPath.FIELD_SUPPLIED,
            notes="Runs and terminations per the cable and hose schedule.",
        )
        for kind, tags in runs.items()
    ]
