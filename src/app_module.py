from ipaddress import IPv4Address
from pathlib import Path

from fastapi import FastAPI
from pydantic_settings import BaseSettings

from src.app_controller import AppController
from src.bom_generator.manifest_module import ManifestModule
from src.call_api.call_api_module import CallApiModule
from src.config import LogLevel, load_config
from src.drawing.drawing_module import DrawingModule
from src.dtm.template_loader import TemplateLoader
from src.grid.grid_module import GridModule
from src.grid.grid_regions_loader import GridRegionsLoader
from src.jobs.jobs_module import JobsModule
from src.module_resolver.module_resolver_module import ModuleResolverModule
from src.sizing.sizing_module import SizingModule


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
        # Same fail-fast contract as the template catalog: GridRegionsLoadError
        # propagates uncaught and crashes startup before any request lands.
        regions_path = repo_root / "config" / "grid_regions.yaml"
        if not regions_path.is_file():
            raise RuntimeError(
                f"grid_regions.yaml missing at {regions_path} — "
                "Dockerfile must COPY it into the image"
            )
        grid_regions = GridRegionsLoader(regions_path).load()
        grid_module = GridModule(regions=grid_regions)
        sizing_module = SizingModule(regions=grid_regions)
        drawing_module = DrawingModule()
        jobs = JobsModule(
            resolver_module=resolver_module,
            manifest_module=manifest_module,
            drawing_module=drawing_module,
            template_catalog=template_catalog,
            grid_regions=grid_regions,
            sizing_service=sizing_module.service,
        )
        app_controller = AppController(
            version=_read_project_version(repo_root),
            template_catalog=template_catalog,
            manifest_url=self.settings.manifest_url,
        )
        app.include_router(app_controller.router)
        app.include_router(call_api.router)
        app.include_router(jobs.router)
        app.include_router(drawing_module.router)
        app.include_router(grid_module.router)
        app.include_router(sizing_module.router)
        # Stash on app.state too — existing tests assert on it.
        app.state.template_catalog = template_catalog

    def create_app(self) -> FastAPI:
        """Create and configure the basic FastAPI application."""
        app = FastAPI()
        self.import_module(app)
        return app


def _read_project_version(repo_root: Path) -> str:
    """Pull `project.version` out of pyproject.toml — single source of truth.

    Returns "unknown" if pyproject is missing/malformed so /healthz still
    answers even if startup config drifts. The deeper failure modes get
    caught by the explicit RuntimeError checks above (catalog, templates).
    """
    import tomllib

    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        return "unknown"
    try:
        data = tomllib.loads(pyproject.read_text())
        version = data.get("project", {}).get("version")
        return str(version) if version else "unknown"
    except (OSError, ValueError):
        return "unknown"
