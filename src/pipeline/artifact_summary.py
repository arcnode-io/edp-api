"""Real per-artifact counts, attached to ArtifactRefs once the pipeline ran."""

from src.bom_generator.bom_models import Bom
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
    plate_qty = {li.part_number: li.qty for li in bom.line_items}

    def summary(ref: ArtifactRef) -> ArtifactSummary | None:
        match ref.kind:
            case ArtifactKind.BOM:
                return ArtifactSummary(
                    line_items=len(bom.line_items),
                    vendors=len({li.vendor for li in bom.line_items}),
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
