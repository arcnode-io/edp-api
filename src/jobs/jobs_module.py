"""DI wiring for jobs."""

from src.bom_generator.manifest_module import ManifestModule
from src.jobs.job_store import JobStore
from src.jobs.jobs_controller import JobsController
from src.jobs.jobs_service import JobsService
from src.module_resolver.module_resolver_module import ModuleResolverModule


class JobsModule:
    """Composes resolver + manifest + store into a JobsService + Controller."""

    def __init__(
        self,
        *,
        resolver_module: ModuleResolverModule,
        manifest_module: ManifestModule,
    ) -> None:
        self.store = JobStore()
        self.service = JobsService(
            resolver=resolver_module.service,
            manifest=manifest_module.service,
            store=self.store,
        )
        self.router = JobsController(self.service).router
