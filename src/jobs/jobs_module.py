"""DI wiring for jobs."""

from src.bom_generator.bom_generator_service import BomGeneratorService
from src.bom_generator.manifest_module import ManifestModule
from src.drawing.drawing_module import DrawingModule
from src.dtm.dtm_generator_service import DtmGeneratorService
from src.jobs.job_store import JobStore
from src.jobs.jobs_controller import JobsController
from src.jobs.jobs_service import JobsService
from src.module_resolver.module_resolver_module import ModuleResolverModule
from src.pipeline.pipeline_service import PipelineService


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
        )
        self.service = JobsService(
            resolver=resolver_module.service,
            client=client,
            pipeline=pipeline,
            store=self.store,
        )
        self.router = JobsController(self.service).router
