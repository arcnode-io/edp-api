"""PipelineService — runs the per-deployment artifact pipeline.

Invoked as a FastAPI BackgroundTask after JobsService.create returns the 202.
For each ArtifactRef in the job's URL list, this:

- BOM artifacts: BomGenerator → JSON → upload to ref.url
- DTM artifacts: DtmGeneratorService → JSON → upload to ref.url
- Other "generated" kinds (SLD, P&ID, comms, installation graph,
  cable/hose schedule): stub-empty bytes for now. Real generators will
  drop in over time without changing the pipeline shape.
- "Selected" URLs (assemblies, plates referenced from the manifest):
  already exist in S3 — skipped.

Selected vs generated is determined by URL prefix: anything under
`s3://arcnode-artifacts/edp/{deployment_id}/` is per-deployment and
needs to be written here; everything else points at the static catalog
maintained by edp-module-assemblies.
"""

import json
import logging
from typing import Final

from src.bom_generator.bom_generator_service import BomGeneratorService
from src.bom_generator.manifest_client import ManifestClient
from src.drawing.sld_hmi_svg_service import SldHmiSvgService
from src.dtm.dtm_generator_service import DtmGeneratorService
from src.shared.enums import DeploymentContext
from src.shared.schemas.artifact import ArtifactKind, ArtifactRef
from src.shared.schemas.configurator_payload import ConfiguratorPayload
from src.shared.schemas.dtm import Dtm
from src.shared.schemas.module_resolution import ModuleResolution

logger = logging.getLogger(__name__)

# URLs under this prefix are per-deployment outputs we generate here. Anything
# else in the artifact list points at the static manifest catalog and already
# exists in S3.
_GENERATED_PREFIX: Final[str] = "s3://arcnode-artifacts/edp/"


class PipelineService:
    """Generates + uploads per-deployment artifacts."""

    def __init__(
        self,
        *,
        client: ManifestClient,
        bom_generator: BomGeneratorService,
        dtm_generator: DtmGeneratorService,
        sld_hmi_svg_service: SldHmiSvgService,
    ) -> None:
        self._client = client
        self._bom = bom_generator
        self._dtm = dtm_generator
        self._sld_hmi = sld_hmi_svg_service

    def run(
        self,
        *,
        payload: ConfiguratorPayload,
        resolution: ModuleResolution,
        urls: list[ArtifactRef],
    ) -> None:
        """Run the full generation pipeline. Raises on any per-artifact failure."""
        profile = resolution.deployment_profile.value
        # Generate DTM once and share with every DTM-aware consumer (the DTM
        # JSON upload + the SLD HMI SVG generator). Saves repeat S3 topology
        # fetches and keeps device_uuids byte-identical across both artifacts.
        dtm = self._dtm.generate(profile=profile, resolution=resolution)
        for ref in urls:
            if not ref.url.startswith(_GENERATED_PREFIX):
                continue  # selected from catalog — already in S3
            self._run_one(
                ref=ref,
                payload=payload,
                resolution=resolution,
                profile=profile,
                dtm=dtm,
            )

    def _run_one(
        self,
        *,
        ref: ArtifactRef,
        payload: ConfiguratorPayload,
        resolution: ModuleResolution,
        profile: str,
        dtm: Dtm,
    ) -> None:
        """Dispatch a single ArtifactRef to its generator (or stub)."""
        if ref.kind == ArtifactKind.BOM and ref.format == "json":
            bom = self._bom.generate(
                deployment_id=payload.deployment_id,
                profile=profile,
                compute_container_qty=resolution.compute_container_count,
                grid_container_qty=1 if resolution.grid_container_present else 0,
                deployment_context=_context_string(payload.deployment_context),
            )
            self._client.upload_bom_json(
                bom.model_dump_json(indent=2).encode("utf-8"), ref.url
            )
            return
        if ref.kind == ArtifactKind.DTM:
            self._client.upload_bytes(
                dtm.model_dump_json(indent=2).encode("utf-8"), ref.url
            )
            return
        if ref.kind == ArtifactKind.SLD_HMI_SVG:
            self._client.upload_bytes(self._sld_hmi.generate(dtm), ref.url)
            return
        # Everything else: stub-empty bytes so downstream consumers (platform-api
        # archive, portal HTML) can fetch by URL. Real generators replace these
        # one kind at a time without changing the pipeline shape.
        self._client.upload_bytes(_stub_body(ref), ref.url)


def _context_string(ctx: DeploymentContext) -> str:
    """Map the deployment_context enum to the BOM generator's string param.

    BomGeneratorService accepts "commercial" or "defense_forward" (drives plate
    variant material/finish). SOVEREIGN_GOVERNMENT collapses to defense for the
    BOM since they share hardware (per the manifest profile alignment).
    """
    if ctx == DeploymentContext.COMMERCIAL:
        return "commercial"
    return "defense_forward"


def _stub_body(ref: ArtifactRef) -> bytes:
    """A minimum-viable byte body for an artifact we don't yet generate.

    JSON formats get a valid empty JSON object; everything else gets a single
    comment-style marker. Keeps `httpx.get(url)` happy in downstream tests
    without lying about the content shape.
    """
    if ref.format == "json":
        return json.dumps({"_stub": True, "kind": ref.kind.value}).encode("utf-8")
    return f"% stub {ref.kind.value} ({ref.format}) — pipeline TODO\n".encode()
