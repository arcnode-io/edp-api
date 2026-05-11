from ipaddress import IPv4Address
from pathlib import Path

from fastapi import FastAPI
from pydantic_settings import BaseSettings

from src.app_controller import AppController
from src.bom_generator.manifest_module import ManifestModule
from src.call_api.call_api_module import CallApiModule
from src.config import LogLevel, load_config
from src.dtm.template_loader import TemplateLoader
from src.jobs.jobs_module import JobsModule
from src.module_resolver.module_resolver_module import ModuleResolverModule


class Settings(BaseSettings):  # type: ignore[explicit-any]  # upstream: pydantic-settings PRs #557/#559 reverted Any fix
    """Application settings with all config values and override capability."""

    log_level: LogLevel
    port: int
    host: IPv4Address
    e2e: bool
    reload: bool
    manifest_url: str


class AppModule:
    """Module for creating basic FastAPI applications.

    `manifest_module_override` lets tests inject a stub-loaded ManifestModule
    so app startup doesn't require S3. Production (None) constructs a real
    ManifestModule that fetches the manifest from `cfg.manifest_url`.
    """

    def __init__(
        self,
        *,
        manifest_module_override: ManifestModule | None = None,
    ) -> None:
        """Initialize the app module with settings."""
        config = load_config()
        self.settings = Settings(
            log_level=config.log_level,
            port=config.port,
            host=config.host,
            e2e=config.e2e,
            reload=config.reload,
            manifest_url=config.manifest_url,
        )
        self._manifest_module_override = manifest_module_override

    def import_module(self, app: FastAPI) -> None:
        """Register routes for app, call_api, and jobs."""
        app_controller = AppController()
        call_api = CallApiModule()
        resolver_module = ModuleResolverModule()
        manifest_module = self._manifest_module_override or ManifestModule(
            manifest_url=self.settings.manifest_url
        )
        # Catalog loaded here (not in create_app) so JobsModule's pipeline
        # can hand it to DtmGeneratorService at wiring time. Process exits
        # on TemplateLoadError so drift surfaces before any DTM emit.
        repo_root = Path(__file__).resolve().parents[1]
        templates_root = repo_root / "device_templates"
        if not templates_root.is_dir():
            raise RuntimeError(
                f"device_templates dir missing at {templates_root} — "
                "Dockerfile must COPY it into the image"
            )
        template_catalog = TemplateLoader(root=templates_root).load_catalog()
        if not template_catalog:
            raise RuntimeError(
                f"empty template catalog from {templates_root} — "
                "no leaf/ or module/ YAML found"
            )
        jobs = JobsModule(
            resolver_module=resolver_module,
            manifest_module=manifest_module,
            template_catalog=template_catalog,
        )
        app.include_router(app_controller.router)
        app.include_router(call_api.router)
        app.include_router(jobs.router)
        # Stash on app.state too — existing tests assert on it.
        app.state.template_catalog = template_catalog

    def create_app(self) -> FastAPI:
        """Create and configure the basic FastAPI application."""
        app = FastAPI()
        self.import_module(app)
        return app
