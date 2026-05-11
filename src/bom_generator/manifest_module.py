"""DI assembly for `ManifestService`.

Two construction paths so tests can bypass the S3 fetch:
- `ManifestModule(manifest_url=...)` — production. Fetches once at construction.
- `ManifestModule.from_manifest(manifest)` — tests. Skips fetch entirely;
  installs a `_StubManifestClient` so downstream pipeline code that calls
  `client.fetch_*` and `client.upload_*` doesn't hit real S3.

JobsModule + (future) BOM/DTM modules consume `module.service` and
`module.client`.
"""

from src.bom_generator.manifest_client import ManifestClient
from src.bom_generator.manifest_models import Manifest
from src.bom_generator.manifest_service import ManifestService


class _StubManifestClient:
    """Test double for ManifestClient — serves an in-memory Manifest, no S3.

    fetch_manifest returns the seeded manifest. The other fetch_* methods
    return empty shapes (BomGenerator + DtmGenerator tolerate empty
    parts/devices and emit empty line-items/devices accordingly). uploads
    are captured in `uploads: dict[url, bytes]` for test assertions.
    """

    def __init__(self, manifest: Manifest) -> None:
        self._manifest = manifest
        self.uploads: dict[str, bytes] = {}

    def fetch_manifest(self) -> Manifest:
        return self._manifest

    def fetch_bom_yaml(self, _url: str) -> dict:
        return {"parts": []}

    def fetch_topology_yaml(self, _url: str) -> dict:
        return {"devices": []}

    def fetch_spec(self, _url: str) -> dict:
        return {}

    def upload_bom_json(self, body: bytes, target_url: str) -> None:
        self.uploads[target_url] = body

    def upload_bytes(self, body: bytes, target_url: str) -> None:
        self.uploads[target_url] = body


class ManifestModule:
    """Single point of DI for the edp-module-assemblies manifest."""

    def __init__(self, *, manifest_url: str) -> None:
        self.client: ManifestClient | _StubManifestClient = ManifestClient(
            manifest_url=manifest_url
        )
        self.service = ManifestService.from_client(self.client)

    @classmethod
    def from_manifest(cls, manifest: Manifest) -> "ManifestModule":
        """Bypass S3 fetch — for tests. Installs a stub client too."""
        instance = cls.__new__(cls)
        instance.client = _StubManifestClient(manifest)
        instance.service = ManifestService(manifest=manifest)
        return instance
