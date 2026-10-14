"""Real per-artifact counts, attached to ArtifactRefs once the pipeline ran."""

from src.bom_generator.bom_models import Bom, ProcurementPath
from src.bom_generator.spec_lines import plate_part_number
from src.cable_hose_schedule.cable_hose_schedule_models import CableHoseSchedule
from src.shared.schemas.artifact import ArtifactKind, ArtifactRef, ArtifactSummary
from src.shared.schemas.dtm import Dtm


def with_summaries(
    urls: list[ArtifactRef],
    *,
    bom: Bom,
    dtm: Dtm,
    cable_hose: CableHoseSchedule,
    deployment_context: str,
) -> list[ArtifactRef]:
    """Copy of `urls` with `summary` set on every kind that has counts."""
    # Reason: a plate appears once per container section (CG on compute and grid)
    plate_qty: dict[str, int] = {}
    for li in bom.line_items:
        plate_qty[li.part_number] = plate_qty.get(li.part_number, 0) + li.qty
    # Manufacturers ARCNODE buys from — not "Customer", "By others", "RFQ"
    vendors = {
        li.vendor
        for li in bom.line_items
        if li.procurement_path
        in (ProcurementPath.CATALOG, ProcurementPath.CUSTOM_FABRICATION)
    }

    def summary(ref: ArtifactRef) -> ArtifactSummary | None:
        match ref.kind:
            case ArtifactKind.BOM:
                return ArtifactSummary(
                    line_items=len(bom.line_items),
                    vendors=len(vendors),
                )
            case ArtifactKind.CABLE_HOSE_SCHEDULE:
                media = {c.cable_type for c in cable_hose.cables} | {
                    h.hose_type for h in cable_hose.hoses
                }
                return ArtifactSummary(
                    runs=len(cable_hose.cables) + len(cable_hose.hoses),
                    media_kinds=len(media),
                )
            case ArtifactKind.DTM:
                return ArtifactSummary(devices=len(dtm.devices), buses=len(dtm.buses))
            case ArtifactKind.INTERFACE_PLATE if ref.plate_id is not None:
                pn = plate_part_number(ref.plate_id, deployment_context)
                return ArtifactSummary(plates=plate_qty[pn])
            case _:
                return None

    return [r.model_copy(update={"summary": summary(r)}) for r in urls]
