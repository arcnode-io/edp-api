"""PipelineService — runs the per-deployment artifact pipeline.

Invoked as a FastAPI BackgroundTask after JobsService.create returns the 202.
For each ArtifactRef in the job's URL list, this:

- BOM artifacts: BomGenerator → JSON → upload to ref.url
- DTM artifacts: DtmGeneratorService → JSON → upload to ref.url
- Other "generated" kinds (SLD, P&ID, comms, installation graph,
  cable/hose schedule): stub-empty bytes for now. Real generators will
  drop in over time without changing the pipeline shape.
- "Selected" URLs (assemblies, plates referenced from the manifest):
  already exist in S3 — skipped.

Selected vs generated is determined by URL prefix: anything under
`s3://arcnode-artifacts/edp/{deployment_id}/` is per-deployment and
needs to be written here; everything else points at the static catalog
maintained by edp-module-assemblies.
"""

import json
import logging
from collections.abc import Callable
from typing import Final

from src.bom_generator.bom_generator_service import (
    BomGeneratorService,
    serialize_bom_xlsx,
)
from src.bom_enrichment.enrichment_service import EnrichmentService
from src.bom_generator.bom_models import Bom
from src.bom_generator.manifest_client import ManifestClient
from src.bom_generator.manifest_models import Manifest
from src.cable_hose_schedule.cable_hose_schedule_models import CableHoseSchedule
from src.cable_hose_schedule.cable_hose_schedule_service import (
    CableHoseScheduleService,
    serialize_cable_hose_schedule_xlsx,
)
from src.drawing.comms_diagram_service import (
    CommsDiagramOutputs,
    CommsDiagramService,
)
from src.drawing.install_graph_service import (
    InstallGraphOutputs,
    InstallGraphService,
)
from src.drawing.pid_cooling_service import PidCoolingOutputs, PidCoolingService
from src.drawing.sld_engineering_service import (
    SldEngineeringOutputs,
    SldEngineeringService,
)
from src.drawing.sld_hmi_svg_service import SldHmiSvgService
from src.dtm.dtm_generator_service import DtmGeneratorService
from src.shared.enums import DeploymentContext
from src.shared.schemas.artifact import ArtifactKind, ArtifactRef
from src.shared.schemas.configurator_payload import ConfiguratorPayload
from src.shared.schemas.dtm import Dtm
from src.shared.schemas.module_resolution import ModuleResolution

logger = logging.getLogger(__name__)

# URLs under this prefix are per-deployment outputs we generate here. Anything
# else in the artifact list points at the static manifest catalog and already
# exists in S3.
_GENERATED_PREFIX: Final[str] = "s3://arcnode-artifacts/edp/"


class PipelineService:
    """Generates + uploads per-deployment artifacts."""

    def __init__(
        self,
        *,
        client: ManifestClient,
        bom_generator: BomGeneratorService,
        dtm_generator: DtmGeneratorService,
        sld_hmi_svg_service: SldHmiSvgService,
        sld_engineering_service: SldEngineeringService,
        pid_cooling_service: PidCoolingService,
        comms_diagram_service: CommsDiagramService,
        cable_hose_schedule_service: CableHoseScheduleService,
        install_graph_service: InstallGraphService,
        enrichment_service: EnrichmentService | None = None,
    ) -> None:
        self._client = client
        self._bom = bom_generator
        self._dtm = dtm_generator
        self._sld_hmi = sld_hmi_svg_service
        self._sld_eng = sld_engineering_service
        self._pid_cooling = pid_cooling_service
        self._comms_diagram = comms_diagram_service
        self._cable_hose = cable_hose_schedule_service
        self._install_graph = install_graph_service
        # None when no distributor creds are configured — pipeline still
        # ships, BOM line_items just have empty `offers` lists.
        self._enrichment = enrichment_service

    def run(
        self,
        *,
        payload: ConfiguratorPayload,
        resolution: ModuleResolution,
        urls: list[ArtifactRef],
        manifest: Manifest,
    ) -> None:
        """Run the full generation pipeline. Raises on any per-artifact failure.

        `manifest` is the snapshot pinned by JobsService at create() — same
        object used to resolve profile→URLs. Passed through to the DTM
        generator so emit doesn't re-fetch S3 (closes ADR-012 torn-read).
        """
        profile = resolution.deployment_profile.value
        # Generate DTM + BOM once and share with every consumer. Saves repeat
        # S3 fetches and keeps content byte-identical across all serializations
        # of the same artifact (e.g. bom.json + bom.xlsx).
        dtm = self._dtm.generate(
            profile=profile, resolution=resolution, manifest=manifest
        )
        bom = self._bom.generate(
            deployment_id=payload.deployment_id,
            profile=profile,
            compute_container_qty=resolution.compute_container_count,
            grid_container_qty=1 if resolution.grid_container_present else 0,
            deployment_context=_context_string(payload.deployment_context),
        )
        # Track-B enrichment: per-distributor offers merged into each line
        # item. No-op when no enrichment service is configured (e.g. when
        # distributor creds aren't set in env).
        if self._enrichment is not None:
            _attach_offers(bom, self._enrichment)
        sld_eng = self._sld_eng.generate(dtm, profile=profile)
        pid_cooling = self._pid_cooling.generate(dtm, profile=profile)
        comms_diagram = self._comms_diagram.generate(dtm, profile=profile)
        cable_hose = self._cable_hose.generate(dtm)
        install_graph = self._install_graph.generate(dtm, profile=profile)
        for ref in urls:
            if not ref.url.startswith(_GENERATED_PREFIX):
                continue  # selected from catalog — already in S3
            self._run_one(
                ref=ref,
                dtm=dtm,
                bom=bom,
                sld_eng=sld_eng,
                pid_cooling=pid_cooling,
                comms_diagram=comms_diagram,
                cable_hose=cable_hose,
                install_graph=install_graph,
            )

    def _run_one(
        self,
        *,
        ref: ArtifactRef,
        dtm: Dtm,
        bom: Bom,
        sld_eng: SldEngineeringOutputs,
        pid_cooling: PidCoolingOutputs,
        comms_diagram: CommsDiagramOutputs,
        cable_hose: CableHoseSchedule,
        install_graph: InstallGraphOutputs,
    ) -> None:
        """Dispatch a single ArtifactRef to its generator (or stub).

        Dispatch table keyed by (kind, format) — adding the next real
        generator means appending one row, not extending an if/elif chain.
        Unmatched (kind, format) pairs fall through to `_stub_body` so
        reserved-but-unimplemented URLs still receive deterministic bytes.
        """
        dispatch: dict[tuple[ArtifactKind, str], Callable[[], bytes]] = {
            (ArtifactKind.BOM, "json"): lambda: bom.model_dump_json(indent=2).encode(
                "utf-8"
            ),
            (ArtifactKind.BOM, "xlsx"): lambda: serialize_bom_xlsx(bom),
            (ArtifactKind.DTM, "json"): lambda: dtm.model_dump_json(indent=2).encode(
                "utf-8"
            ),
            (ArtifactKind.SLD_HMI_SVG, "svg"): lambda: self._sld_hmi.generate(dtm),
            (ArtifactKind.SLD, "dxf"): lambda: sld_eng.dxf,
            (ArtifactKind.SLD, "pdf"): lambda: sld_eng.pdf,
            (ArtifactKind.PID_COOLING, "dxf"): lambda: pid_cooling.dxf,
            (ArtifactKind.PID_COOLING, "pdf"): lambda: pid_cooling.pdf,
            (ArtifactKind.COMMS_DIAGRAM, "dxf"): lambda: comms_diagram.dxf,
            (ArtifactKind.COMMS_DIAGRAM, "pdf"): lambda: comms_diagram.pdf,
            (
                ArtifactKind.CABLE_HOSE_SCHEDULE,
                "json",
            ): lambda: cable_hose.model_dump_json(indent=2).encode("utf-8"),
            (
                ArtifactKind.CABLE_HOSE_SCHEDULE,
                "xlsx",
            ): lambda: serialize_cable_hose_schedule_xlsx(cable_hose),
            (ArtifactKind.INSTALLATION_GRAPH, "dxf"): lambda: install_graph.dxf,
            (ArtifactKind.INSTALLATION_GRAPH, "pdf"): lambda: install_graph.pdf,
        }
        builder = dispatch.get((ref.kind, ref.format))
        body = builder() if builder is not None else _stub_body(ref)
        # `upload_bom_json` is just an alias for `upload_bytes` today; uses
        # the same boto3 put_object under the hood. Funnel everything through
        # `upload_bytes` for a single I/O path.
        self._client.upload_bytes(body, ref.url)


def _attach_offers(bom: Bom, enrichment: EnrichmentService) -> None:
    """Fetch per-MPN offers across all configured distributors, merge into BOM.

    Looks up by `BomLineItem.part_number` (which IS the MPN for catalog
    items per `BomGeneratorService._spec_to_catalog_line`). Custom-fab
    lines (ARCNODE plates) are skipped — no external distributor offer
    exists. Each line's `offers` field gets the full list of returned
    offers (including error-offers, so a reviewer sees which distributors
    failed for this MPN).
    """
    catalog_mpns = sorted(
        {
            li.part_number
            for li in bom.line_items
            if li.procurement_path.value == "catalog"
        }
    )
    if not catalog_mpns:
        return
    enriched = enrichment.enrich(catalog_mpns)
    for line in bom.line_items:
        result = enriched.get(line.part_number)
        if result is not None:
            line.offers = result.offers


def _context_string(ctx: DeploymentContext) -> str:
    """Map the deployment_context enum to the BOM generator's string param.

    BomGeneratorService accepts "commercial" or "defense_forward" (drives plate
    variant material/finish). SOVEREIGN_GOVERNMENT collapses to defense for the
    BOM since they share hardware (per the manifest profile alignment).
    """
    if ctx == DeploymentContext.COMMERCIAL:
        return "commercial"
    return "defense_forward"


def _stub_body(ref: ArtifactRef) -> bytes:
    """A minimum-viable byte body for an artifact we don't yet generate.

    JSON formats get a valid empty JSON object; everything else gets a single
    comment-style marker. Keeps `httpx.get(url)` happy in downstream tests
    without lying about the content shape.
    """
    if ref.format == "json":
        return json.dumps({"_stub": True, "kind": ref.kind.value}).encode("utf-8")
    return f"% stub {ref.kind.value} ({ref.format}) — pipeline TODO\n".encode()
