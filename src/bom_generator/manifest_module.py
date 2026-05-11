"""DI assembly for `ManifestService`.

Two construction paths so tests can bypass the S3 fetch:
- `ManifestModule(manifest_url=...)` — production. Fetches once at construction.
- `ManifestModule.from_manifest(manifest)` — tests. Skips fetch entirely.

JobsModule + (future) BOM/DTM modules consume `module.service`.
"""

from src.bom_generator.manifest_client import ManifestClient
from src.bom_generator.manifest_models import Manifest
from src.bom_generator.manifest_service import ManifestService


class ManifestModule:
    """Single point of DI for the edp-module-assemblies manifest."""

    def __init__(self, *, manifest_url: str) -> None:
        self.service = ManifestService.from_client(
            ManifestClient(manifest_url=manifest_url)
        )

    @classmethod
    def from_manifest(cls, manifest: Manifest) -> "ManifestModule":
        """Bypass S3 fetch — for tests + dev paths that pre-load a fixture."""
        instance = cls.__new__(cls)
        instance.service = ManifestService(manifest=manifest)
        return instance
