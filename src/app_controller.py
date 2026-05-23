from classy_fastapi import Routable, get
from fastapi import Response
from pydantic import BaseModel

from src.shared.schemas.template import DeviceTemplate


class TemplateCatalogStatus(BaseModel):
    """Catalog-loaded status surfaced by /healthz."""

    size: int
    sample: list[str]  # first few template slugs — sanity check loader picked stuff up


class HealthzResponse(BaseModel):
    """Deep health-check body. Surfaces enough to triage 'is this pod sick' without S3 calls."""

    status: str
    version: str
    template_catalog: TemplateCatalogStatus
    manifest_url: str


class AppController(Routable):
    """Root-level routes: liveness `/` + deep readiness `/healthz`."""

    def __init__(
        self,
        *,
        version: str,
        template_catalog: dict[str, DeviceTemplate],
        manifest_url: str,
    ) -> None:
        super().__init__()
        self._version = version
        self._catalog = template_catalog
        self._manifest_url = manifest_url

    @get("/")
    def healthcheck(self) -> Response:
        """Liveness probe — bytes-thin, no I/O, just proves the process is up."""
        return Response("ok")

    @get("/healthz")
    def healthz(self) -> HealthzResponse:
        """Readiness — surfaces version + catalog load + manifest-url config.

        Intentionally does NOT round-trip S3. Manifest is fetched per-job at
        JobsService.create; healthz reflects startup config only.
        """
        sample = sorted(self._catalog)[:3]
        return HealthzResponse(
            status="ok",
            version=self._version,
            template_catalog=TemplateCatalogStatus(
                size=len(self._catalog), sample=sample
            ),
            manifest_url=self._manifest_url,
        )
