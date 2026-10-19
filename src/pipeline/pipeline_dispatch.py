"""Bytes for each artifact URL, by (kind, format).

Split out of pipeline_service.py (200-line budget). Adding the next real
generator means appending one row, not extending an if/elif chain.
"""

import json
from collections.abc import Callable

from src.bom_generator.bom_models import Bom
from src.bom_generator.bom_xlsx import serialize_bom_xlsx
from src.cable_hose_schedule.cable_hose_schedule_models import CableHoseSchedule
from src.cable_hose_schedule.cable_hose_schedule_service import (
    serialize_cable_hose_schedule_xlsx,
)
from src.drawing.comms_diagram_service import CommsDiagramOutputs
from src.drawing.install_sequence_service import (
    InstallSequenceOutputs,
    serialize_install_sequence_xlsx,
)
from src.drawing.pid_cooling_service import PidCoolingOutputs
from src.drawing.sld_engineering_service import SldEngineeringOutputs
from src.drawing.sld_hmi_svg_service import SldHmiSvgService
from src.shared.schemas.artifact import ArtifactKind, ArtifactRef
from src.shared.schemas.dtm import Dtm


def artifact_bytes(
    ref: ArtifactRef,
    *,
    dtm: Dtm,
    bom: Bom,
    sld_hmi: SldHmiSvgService,
    sld_eng: SldEngineeringOutputs,
    pid_cooling: PidCoolingOutputs,
    comms_diagram: CommsDiagramOutputs,
    cable_hose: CableHoseSchedule,
    install_sequence: InstallSequenceOutputs,
) -> bytes:
    """The body to upload for one ArtifactRef; a stub for unmatched pairs."""
    dispatch: dict[tuple[ArtifactKind, str], Callable[[], bytes]] = {
        (ArtifactKind.BOM, "json"): lambda: bom.model_dump_json(indent=2).encode(
            "utf-8"
        ),
        (ArtifactKind.BOM, "xlsx"): lambda: serialize_bom_xlsx(bom),
        (ArtifactKind.DTM, "json"): lambda: dtm.model_dump_json(indent=2).encode(
            "utf-8"
        ),
        (ArtifactKind.SLD_HMI_SVG, "svg"): lambda: sld_hmi.generate(dtm),
        (ArtifactKind.SLD, "dxf"): lambda: sld_eng.dxf,
        (ArtifactKind.SLD, "pdf"): lambda: sld_eng.pdf,
        (ArtifactKind.PID_COOLING, "dxf"): lambda: pid_cooling.dxf,
        (ArtifactKind.PID_COOLING, "pdf"): lambda: pid_cooling.pdf,
        (ArtifactKind.COMMS_DIAGRAM, "dxf"): lambda: comms_diagram.dxf,
        (ArtifactKind.COMMS_DIAGRAM, "pdf"): lambda: comms_diagram.pdf,
        (
            ArtifactKind.CABLE_HOSE_SCHEDULE,
            "json",
        ): lambda: cable_hose.model_dump_json(
            indent=2
        ).encode("utf-8"),
        (
            ArtifactKind.CABLE_HOSE_SCHEDULE,
            "xlsx",
        ): lambda: serialize_cable_hose_schedule_xlsx(cable_hose),
        (ArtifactKind.INSTALL_SEQUENCE, "pdf"): lambda: install_sequence.pdf,
        (
            ArtifactKind.INSTALL_SEQUENCE,
            "xlsx",
        ): lambda: serialize_install_sequence_xlsx(dtm),
    }
    builder = dispatch.get((ref.kind, ref.format))
    return builder() if builder is not None else _stub_body(ref)


def _stub_body(ref: ArtifactRef) -> bytes:
    """A minimum-viable byte body for an artifact we don't yet generate.

    JSON formats get a valid empty JSON object; everything else gets a single
    comment-style marker. Keeps `httpx.get(url)` happy in downstream tests
    without lying about the content shape.
    """
    if ref.format == "json":
        return json.dumps({"_stub": True, "kind": ref.kind.value}).encode("utf-8")
    return f"% stub {ref.kind.value} ({ref.format}) — pipeline TODO\n".encode()
