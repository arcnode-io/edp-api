"""A ManifestClient over a local edp-module-assemblies checkout (no S3).

CI clones assemblies main to EDP_MODULE_ASSEMBLIES_DIR; locally the sibling
checkout is used. Plate specs live in edp-interface-plates and come back
empty, which only affects plate material/finish text.
"""

import os
from pathlib import Path
from typing import Final

import yaml

from src.bom_generator.manifest_models import Manifest

REPO: Final[Path] = Path(
    os.environ.get(
        "EDP_MODULE_ASSEMBLIES_DIR",
        Path(__file__).resolve().parents[2] / "edp-module-assemblies",
    )
)
_S3: Final[str] = "s3://arcnode-artifacts/"


class AssembliesCheckoutClient:
    """Serves manifest, bom.yaml, topology.yaml and specs from the checkout."""

    def __init__(self) -> None:
        self.uploads: dict[str, bytes] = {}
        self._manifest = Manifest.model_validate(
            yaml.safe_load((REPO / "manifest.yaml").read_text())
        )

    def fetch_manifest(self) -> Manifest:
        """The checkout's manifest.yaml."""
        return self._manifest

    def fetch_bom_yaml(self, url: str) -> dict:
        """A variant's bom.yaml."""
        return yaml.safe_load(self._local(url).read_text())

    def fetch_topology_yaml(self, url: str) -> dict:
        """A variant's topology.yaml."""
        return yaml.safe_load(self._local(url).read_text())

    def fetch_spec(self, url: str) -> dict:
        """An equipment spec; plate specs come back empty."""
        if "/plates/" in url:
            return {}
        return yaml.safe_load(self._local(url).read_text())

    def upload_bytes(self, body: bytes, target_url: str) -> None:
        """Keep the upload in memory."""
        self.uploads[target_url] = body

    def upload_bom_json(self, body: bytes, target_url: str) -> None:
        """Keep the upload in memory."""
        self.uploads[target_url] = body

    def _local(self, url: str) -> Path:
        return REPO / url.removeprefix(_S3)
