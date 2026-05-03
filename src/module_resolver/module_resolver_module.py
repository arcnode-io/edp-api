"""DI wiring for module_resolver."""

from src.module_resolver.module_resolver_service import ModuleResolverService


class ModuleResolverModule:
    """Instantiates ModuleResolverService for downstream modules."""

    def __init__(self) -> None:
        self.service = ModuleResolverService()
