"""PipelineService — runs the per-deployment artifact pipeline.

Invoked as a FastAPI BackgroundTask after JobsService.create returns the 202.
Builds the DTM, cable/hose schedule, BOM and drawings once, then uploads the
bytes for every per-deployment URL (`s3://arcnode-artifacts/edp/...`).
URLs elsewhere point at the edp-module-assemblies catalog, already in S3.
"""

import logging
from typing import Final

from src.bom_generator.bom_generator_service import (
    BomGeneratorService,
)
from src.bom_enrichment.enrichment_service import EnrichmentService
from src.bom_generator.cable_hose_lines import cable_hose_lines
from src.bom_generator.manifest_client import ManifestClient
from src.bom_generator.manifest_models import Manifest
from src.cable_hose_schedule.cable_hose_schedule_service import (
    CableHoseScheduleService,
)
from src.drawing.comms_diagram_service import (
    CommsDiagramService,
)
from src.drawing.install_sequence_service import (
    InstallSequenceService,
)
from src.drawing.pid_cooling_service import PidCoolingService
from src.drawing.sld_engineering_service import (
    SldEngineeringService,
)
from src.drawing.sld_hmi_svg_service import SldHmiSvgService
from src.dtm.dtm_generator_service import DtmGeneratorService
from src.pipeline.artifact_summary import with_summaries
from src.pipeline.pipeline_bom import attach_offers, bom_order, context_string
from src.pipeline.pipeline_dispatch import artifact_bytes
from src.shared.schemas.artifact import ArtifactRef
from src.shared.schemas.configurator_payload import ConfiguratorPayload
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
        install_sequence_service: InstallSequenceService,
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
        self._install_sequence = install_sequence_service
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
    ) -> list[ArtifactRef]:
        """Run the full generation pipeline. Raises on any per-artifact failure.

        Returns `urls` with each ref's real counts attached (`summary`).

        `manifest` is the snapshot pinned by JobsService at create() — same
        object used to resolve profile→URLs. Passed through to the DTM
        generator so emit doesn't re-fetch S3 (closes ADR-011 torn-read).
        """
        profile = resolution.deployment_profile.value
        # Generate DTM + BOM once and share with every consumer. Saves repeat
        # S3 fetches and keeps content byte-identical across all serializations
        # of the same artifact (e.g. bom.json + bom.xlsx).
        dtm = self._dtm.generate(
            profile=profile, resolution=resolution, manifest=manifest
        )
        cable_hose = self._cable_hose.generate(dtm)
        bom = self._bom.generate(
            deployment_id=payload.deployment_id,
            profile=profile,
            gpu_variant=resolution.gpu_variant,
            order=bom_order(payload, resolution),
            compute_container_qty=resolution.compute_container_count,
            grid_container_qty=resolution.grid_container_count,
            deployment_context=context_string(payload.deployment_context),
            field_lines=cable_hose_lines(cable_hose),
        )
        # Track-B enrichment: per-distributor offers merged into each line
        # item. No-op when no enrichment service is configured (e.g. when
        # distributor creds aren't set in env).
        if self._enrichment is not None:
            attach_offers(bom, self._enrichment)
        sld_eng = self._sld_eng.generate(dtm, bom=bom, profile=profile)
        pid_cooling = self._pid_cooling.generate(dtm, profile=profile)
        comms_diagram = self._comms_diagram.generate(dtm, bom=bom, profile=profile)
        install_sequence = self._install_sequence.generate(dtm, profile=profile)
        for ref in urls:
            if not ref.url.startswith(_GENERATED_PREFIX):
                continue  # selected from catalog — already in S3
            body = artifact_bytes(
                ref,
                dtm=dtm,
                bom=bom,
                sld_hmi=self._sld_hmi,
                sld_eng=sld_eng,
                pid_cooling=pid_cooling,
                comms_diagram=comms_diagram,
                cable_hose=cable_hose,
                install_sequence=install_sequence,
            )
            self._client.upload_bytes(body, ref.url)
        return with_summaries(
            urls,
            bom=bom,
            dtm=dtm,
            cable_hose=cable_hose,
            deployment_context=context_string(payload.deployment_context),
        )
