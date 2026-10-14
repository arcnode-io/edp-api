"""BOM generator service.

Per Q9-C: fetches manifest, resolves profile→assets, fetches each
referenced spec.yaml + bom.yaml, transforms into bom.json per Q17-A.

Entry: BomGeneratorService.generate(deployment_id, profile, manifest_url,
container_counts) → Bom (uploaded to S3 by caller).
"""

import json
import logging
from datetime import UTC, datetime
from uuid import UUID

from src.shared.enums import GpuVariant
from src.bom_generator.bom_container_lines import ContainerGroup, section_lines
from src.bom_generator.bom_models import (
    Bom,
    BomLineItem,
    BomOrder,
    BomSection,
)
from src.bom_generator.bom_site_lines import site_lines
from src.bom_generator.manifest_client import ManifestClient
from src.bom_generator.spec_lines import (
    plate_spec_to_custom_line,
    shell_to_custom_line,
    spec_to_catalog_line,
)
from src.bom_generator.manifest_models import Manifest, ProfileAssemblies

logger = logging.getLogger(__name__)


class BomGeneratorService:
    """Generates a deployment BOM from manifest + per-assembly bom.yaml."""

    def __init__(self, manifest_client: ManifestClient) -> None:
        self._client = manifest_client

    def generate(
        self,
        *,
        deployment_id: UUID,
        profile: str,
        gpu_variant: GpuVariant,
        order: BomOrder,
        compute_container_qty: int = 1,
        grid_container_qty: int = 1,
        deployment_context: str = "commercial",
        field_lines: list[BomLineItem] | None = None,
    ) -> Bom:
        """Build a sectioned Bom for the given deployment.

        Args:
            deployment_id: UUID of the deployment job.
            profile: Profile name (e.g. "commercial_ac"). Must exist in manifest.
            gpu_variant: Ordered GPU type; picks the compute container variant.
            order: The order as placed and delivered (BOM header, site lines).
            compute_container_qty: Number of compute containers.
            grid_container_qty: Number of grid containers (primary + feeders).
            deployment_context: Drives plate variant material/finish.
            field_lines: Installer-supplied material (cables, hoses).

        Returns:
            Bom grouped compute → grid → site → field, items numbered.
        """
        manifest = self._client.fetch_manifest()
        if profile not in manifest.profiles:
            raise ValueError(
                f"profile {profile!r} not in manifest (available: {sorted(manifest.profiles)})"
            )
        prof = manifest.profiles[profile]
        groups = self._container_groups(
            manifest, prof, gpu_variant, compute_container_qty, grid_container_qty
        )

        def part_line(
            eid: str, qty: int, section: BomSection, ref: str
        ) -> BomLineItem | None:
            spec_url = manifest.specs.get(eid)
            if spec_url is None:
                raise ValueError(f"no equipment spec in the manifest for {eid}")
            return spec_to_catalog_line(
                self._client.fetch_spec(spec_url), qty, section, ref
            )

        def plate_line(
            pid: str, qty: int, section: BomSection, ref: str
        ) -> BomLineItem | None:
            urls = manifest.plates[pid]
            spec = self._client.fetch_spec(urls.spec)
            return plate_spec_to_custom_line(
                pid, spec, urls.step, qty, section, ref, deployment_context
            )

        lines: list[BomLineItem] = []
        for section in (BomSection.COMPUTE, BomSection.GRID):
            lines += section_lines(
                [g for g in groups if g.section == section],
                shell_line=shell_to_custom_line,
                part_line=part_line,
                plate_line=plate_line,
            )
        lines += site_lines(order, compute_container_qty, grid_container_qty)
        lines += field_lines or []
        return Bom(
            deployment_id=deployment_id,
            profile=profile,
            manifest_version=manifest.version,
            generated_at=datetime.now(UTC),
            compute_container_qty=compute_container_qty,
            grid_container_qty=grid_container_qty,
            order=order,
            line_items=_numbered(lines),
        )

    def _container_groups(
        self,
        manifest: Manifest,
        prof: ProfileAssemblies,
        gpu_variant: GpuVariant,
        compute_qty: int,
        grid_qty: int,
    ) -> list[ContainerGroup]:
        """Compute C1-CN; grid G1 (primary, POI meter) + G2-GM feeders."""
        wanted = [
            (
                BomSection.COMPUTE,
                "C",
                1,
                compute_qty,
                "compute_container",
                prof.compute_variant(gpu_variant),
            ),
        ]
        if prof.grid_container is not None:
            wanted.append(
                (BomSection.GRID, "G", 1, 1, "grid_container", prof.grid_container)
            )
            if grid_qty > 1:
                if prof.grid_feeder_container is None:
                    raise ValueError(
                        f"{grid_qty} grid containers but no feeder variant"
                    )
                wanted.append(
                    (
                        BomSection.GRID,
                        "G",
                        2,
                        grid_qty,
                        "grid_container",
                        prof.grid_feeder_container,
                    )
                )
        return [
            ContainerGroup(
                section,
                prefix,
                first,
                last,
                self._client.fetch_bom_yaml(manifest.assemblies[kind][name].bom),
            )
            for section, prefix, first, last, kind, name in wanted
        ]


def _numbered(lines: list[BomLineItem]) -> list[BomLineItem]:
    """Item numbers 1..n in section order (compute, grid, site, field)."""
    order = list(BomSection)
    ranked = sorted(lines, key=lambda li: order.index(li.section))
    return [li.model_copy(update={"item": i}) for i, li in enumerate(ranked, start=1)]


def serialize_bom(bom: Bom) -> bytes:
    """Serialize a Bom to JSON bytes for S3 upload."""
    return json.dumps(bom.model_dump(mode="json"), indent=2).encode("utf-8")
