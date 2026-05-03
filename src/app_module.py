from fastapi import FastAPI
from src.app_controller import AppController
from src.call_api.call_api_module import CallApiModule
from src.config import load_config, LogLevel
from src.hardware_selector.hardware_selector_module import HardwareSelectorModule
from src.jobs.jobs_module import JobsModule
from src.module_resolver.module_resolver_module import ModuleResolverModule
from pydantic_settings import BaseSettings
from ipaddress import IPv4Address


class Settings(BaseSettings):  # type: ignore[explicit-any]  # upstream: pydantic-settings PRs #557/#559 reverted Any fix
    """Application settings with all config values and override capability."""

    log_level: LogLevel
    port: int
    host: IPv4Address
    e2e: bool
    reload: bool


class AppModule:
    """Module for creating basic FastAPI applications."""

    def __init__(self) -> None:
        """Initialize the app module with settings."""
        config = load_config()
        self.settings = Settings(
            log_level=config.log_level,
            port=config.port,
            host=config.host,
            e2e=config.e2e,
            reload=config.reload,
        )

    def import_module(self, app: FastAPI) -> None:
        """Register routes for app, call_api, and jobs."""
        app_controller = AppController()
        call_api = CallApiModule()
        resolver_module = ModuleResolverModule()
        selector_module = HardwareSelectorModule()
        jobs = JobsModule(
            resolver_module=resolver_module,
            selector_module=selector_module,
        )
        app.include_router(app_controller.router)
        app.include_router(call_api.router)
        app.include_router(jobs.router)

    def create_app(self) -> FastAPI:
        """Create and configure the basic FastAPI application."""
        app = FastAPI()
        self.import_module(app)
        return app
