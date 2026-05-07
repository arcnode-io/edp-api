"""S3 client wrapper for fetching `manifest.yaml` and referenced `spec.yaml` files.

Pure I/O — pulls bytes from S3, deserializes via Pydantic. Backend selected
via env var (S3_ENDPOINT_URL for localstack tests; default real S3).
"""

import os
from typing import Final

import boto3
import yaml
from botocore.client import BaseClient

from src.bom_generator.manifest_models import Manifest

_BUCKET_PREFIX: Final[str] = "s3://"


def _make_client() -> BaseClient:
    """Create S3 client honoring optional localstack endpoint override."""
    endpoint = os.environ.get("S3_ENDPOINT_URL")
    if endpoint:
        return boto3.client(  # nosec B106 — localstack-only literal credentials
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id="test",
            aws_secret_access_key="test",  # noqa: S106 — localstack-only literal
            region_name="us-east-1",
        )
    return boto3.client("s3")


def _split_s3_url(url: str) -> tuple[str, str]:
    """`s3://bucket/key/path` → (bucket, key)."""
    if not url.startswith(_BUCKET_PREFIX):
        raise ValueError(f"not an s3:// URL: {url}")
    rest = url[len(_BUCKET_PREFIX) :]
    bucket, _, key = rest.partition("/")
    return bucket, key


class ManifestClient:
    """Fetches manifest + specs from S3, with simple in-memory cache per instance."""

    def __init__(self, manifest_url: str, s3: BaseClient | None = None) -> None:
        self._manifest_url = manifest_url
        self._s3 = s3 if s3 is not None else _make_client()
        self._spec_cache: dict[str, dict] = {}

    def fetch_manifest(self) -> Manifest:
        """Fetch + parse manifest.yaml."""
        bucket, key = _split_s3_url(self._manifest_url)
        body = self._s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        return Manifest.model_validate(yaml.safe_load(body))

    def fetch_spec(self, spec_url: str) -> dict:
        """Fetch + parse spec.yaml; cached by URL within client lifetime."""
        if spec_url in self._spec_cache:
            return self._spec_cache[spec_url]
        bucket, key = _split_s3_url(spec_url)
        body = self._s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        parsed = yaml.safe_load(body)
        self._spec_cache[spec_url] = parsed
        return parsed

    def fetch_bom_yaml(self, bom_url: str) -> dict:
        """Fetch + parse an assembly bom.yaml."""
        bucket, key = _split_s3_url(bom_url)
        body = self._s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        return yaml.safe_load(body)

    def fetch_topology_yaml(self, topology_url: str) -> dict:
        """Fetch + parse an assembly topology.yaml."""
        bucket, key = _split_s3_url(topology_url)
        body = self._s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        return yaml.safe_load(body)

    def upload_bom_json(self, bom_json_bytes: bytes, target_url: str) -> None:
        """Upload generated bom.json to S3."""
        bucket, key = _split_s3_url(target_url)
        self._s3.put_object(Bucket=bucket, Key=key, Body=bom_json_bytes)
