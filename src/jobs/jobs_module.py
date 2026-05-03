"""DI wiring for jobs."""

from src.hardware_selector.hardware_selector_module import HardwareSelectorModule
from src.jobs.job_store import JobStore
from src.jobs.jobs_controller import JobsController
from src.jobs.jobs_service import JobsService
from src.module_resolver.module_resolver_module import ModuleResolverModule


class JobsModule:
    """Composes resolver + selector + store into a JobsService + Controller."""

    def __init__(
        self,
        *,
        resolver_module: ModuleResolverModule,
        selector_module: HardwareSelectorModule,
    ) -> None:
        self.store = JobStore()
        self.service = JobsService(
            resolver=resolver_module.service,
            selector=selector_module.service,
            store=self.store,
        )
        self.router = JobsController(self.service).router
