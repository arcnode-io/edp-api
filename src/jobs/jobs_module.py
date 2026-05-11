"""DI wiring for jobs."""

from src.bom_generator.bom_generator_service import BomGeneratorService
from src.bom_generator.manifest_module import ManifestModule
from src.dtm.dtm_generator_service import DtmGeneratorService
from src.dtm.template_loader import TemplateLoader
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
        template_catalog: dict,
    ) -> None:
        self.store = JobStore()
        # Pipeline shares the manifest_module's underlying ManifestClient so
        # the in-memory Manifest cache is reused — no second S3 fetch.
        client = manifest_module.client
        pipeline = PipelineService(
            client=client,
            bom_generator=BomGeneratorService(client),
            dtm_generator=DtmGeneratorService(client, template_catalog=template_catalog),
        )
        self.service = JobsService(
            resolver=resolver_module.service,
            manifest=manifest_module.service,
            pipeline=pipeline,
            store=self.store,
        )
        self.router = JobsController(self.service).router
