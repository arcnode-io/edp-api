"""DI wiring for jobs."""

import logging
import os

from src.bom_enrichment._base_scraper import DistributorClient
from src.bom_enrichment._graybar_client import GraybarClient
from src.bom_enrichment.enrichment_service import EnrichmentService
from src.bom_generator.bom_generator_service import BomGeneratorService
from src.bom_generator.manifest_module import ManifestModule
from src.cable_hose_schedule.cable_hose_schedule_service import CableHoseScheduleService
from src.drawing.drawing_module import DrawingModule
from src.dtm.dtm_generator_service import DtmGeneratorService
from src.jobs.job_store import JobStore
from src.jobs.jobs_controller import JobsController
from src.jobs.jobs_service import JobsService
from src.module_resolver.module_resolver_module import ModuleResolverModule
from src.pipeline.pipeline_service import PipelineService

logger = logging.getLogger(__name__)


class JobsModule:
    """Composes resolver + manifest + pipeline + store into JobsService + Controller."""

    def __init__(
        self,
        *,
        resolver_module: ModuleResolverModule,
        manifest_module: ManifestModule,
        drawing_module: DrawingModule,
        template_catalog: dict,
    ) -> None:
        self.store = JobStore()
        # Pipeline and JobsService share the same ManifestClient. JobsService
        # calls fetch_manifest() per create() and pins the result on the
        # JobRecord; the pipeline then re-uses that pin (no second fetch).
        # The client's other fetch_* methods (topology.yaml, spec.yaml,
        # bom.yaml) are still called per-pipeline by BOM/DTM generators.
        client = manifest_module.client
        pipeline = PipelineService(
            client=client,
            bom_generator=BomGeneratorService(client),
            dtm_generator=DtmGeneratorService(
                client, template_catalog=template_catalog
            ),
            sld_hmi_svg_service=drawing_module.sld_hmi_svg,
            sld_engineering_service=drawing_module.sld_engineering,
            pid_cooling_service=drawing_module.pid_cooling,
            comms_diagram_service=drawing_module.comms_diagram,
            cable_hose_schedule_service=CableHoseScheduleService(),
            install_graph_service=drawing_module.install_graph,
            enrichment_service=_build_enrichment_service(),
        )
        self.service = JobsService(
            resolver=resolver_module.service,
            client=client,
            pipeline=pipeline,
            store=self.store,
        )
        self.router = JobsController(self.service).router


def _build_enrichment_service() -> EnrichmentService | None:
    """Construct EnrichmentService with whichever distributor clients have creds.

    Each distributor is opt-in via env vars. Missing creds for a distributor
    just skips it — no error, no fallback. If no distributor is configured,
    returns None and the pipeline skips enrichment entirely.
    """
    clients: list[DistributorClient] = []
    if os.environ.get("GRAYBAR_USER") and os.environ.get("GRAYBAR_PASS"):
        clients.append(GraybarClient())
    # Anixter / Insight / Mouser / CDW lands as those clients ship.
    if not clients:
        logger.info("no distributor creds in env; BOM enrichment disabled")
        return None
    return EnrichmentService(clients)
