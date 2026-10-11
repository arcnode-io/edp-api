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

from src.bom_generator.bom_models import (
    Bom,
    BomLineItem,
)
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
        compute_container_qty: int = 1,
        grid_container_qty: int = 1,
        deployment_context: str = "commercial",
    ) -> Bom:
        """Build a Bom for the given deployment.

        Args:
            deployment_id: UUID of the deployment job.
            profile: Profile name (e.g. "commercial_ac"). Must exist in manifest.
            compute_container_qty: Number of compute containers.
            grid_container_qty: Number of grid containers (0 if no_bess).
            deployment_context: Drives plate variant material/finish.

        Returns:
            Populated Bom ready for serialization.
        """
        manifest = self._client.fetch_manifest()
        if profile not in manifest.profiles:
            raise ValueError(
                f"profile {profile!r} not in manifest (available: {sorted(manifest.profiles)})"
            )
        prof = manifest.profiles[profile]

        boms = self._container_boms(
            manifest, prof, compute_container_qty, grid_container_qty
        )
        parts = _sum_by(boms, "parts", "equipment_id")
        line_items = _shell_lines(boms)
        line_items += self._parts_to_lines(
            manifest, [{"equipment_id": eid, "qty": q} for eid, q in parts.items()], 1
        )
        line_items.extend(
            self._plate_lines(
                manifest, _sum_by(boms, "plates", "id"), deployment_context
            )
        )

        return Bom(
            deployment_id=deployment_id,
            profile=profile,
            manifest_version=manifest.version,
            generated_at=datetime.now(UTC),
            compute_container_qty=compute_container_qty,
            grid_container_qty=grid_container_qty,
            line_items=line_items,
        )

    def _container_boms(
        self,
        manifest: Manifest,
        prof: ProfileAssemblies,
        compute_qty: int,
        grid_qty: int,
    ) -> list[tuple[dict, int]]:
        """Each container variant's bom.yaml, paired with how many the site gets.

        Grid = one primary (carries the POI meter) + feeders for the rest.
        """
        wanted = [("compute_container", prof.compute_container, compute_qty)]
        if prof.grid_container is not None and grid_qty > 0:
            wanted.append(("grid_container", prof.grid_container, 1))
            if grid_qty > 1:
                if prof.grid_feeder_container is None:
                    raise ValueError(
                        f"{grid_qty} grid containers but no feeder variant"
                    )
                wanted.append(
                    ("grid_container", prof.grid_feeder_container, grid_qty - 1)
                )
        boms: list[tuple[dict, int]] = []
        for kind, name, qty in wanted:
            variant = manifest.assemblies.get(kind, {}).get(name)
            if variant is None:
                logger.warning(f"{kind} variant {name} missing")
                continue
            boms.append((self._client.fetch_bom_yaml(variant.bom), qty))
        return boms

    def _parts_to_lines(
        self, manifest: Manifest, parts: list[dict], container_qty: int
    ) -> list[BomLineItem]:
        lines: list[BomLineItem] = []
        for part in parts:
            equipment_id = part["equipment_id"]
            per_container_qty = part["qty"]
            spec_url = manifest.specs.get(equipment_id)
            if spec_url is None:
                logger.warning(f"spec URL missing for {equipment_id}")
                continue
            spec = self._client.fetch_spec(spec_url)
            lines.append(spec_to_catalog_line(spec, per_container_qty * container_qty))
        return lines

    def _plate_lines(
        self,
        manifest: Manifest,
        plate_qty: dict[str, int],
        deployment_context: str,
    ) -> list[BomLineItem]:
        lines: list[BomLineItem] = []
        for plate_id, qty in plate_qty.items():
            urls = manifest.plates.get(plate_id)
            if urls is None:
                logger.warning(f"plate {plate_id} not in manifest")
                continue
            plate_spec = self._client.fetch_spec(urls.spec)
            lines.append(
                plate_spec_to_custom_line(
                    plate_id=plate_id,
                    plate_spec=plate_spec,
                    plate_step_url=urls.step,
                    qty=qty,
                    deployment_context=deployment_context,
                )
            )
        return lines


def _sum_by(boms: list[tuple[dict, int]], section: str, key: str) -> dict[str, int]:
    """Total qty per id across containers. Reason: containers share parts and
    plates (CG is on every container), and each id should be one BOM line."""
    totals: dict[str, int] = {}
    for bom_yaml, container_qty in boms:
        for item in bom_yaml.get(section, []):
            totals[item[key]] = totals.get(item[key], 0) + item["qty"] * container_qty
    return totals


def _shell_lines(boms: list[tuple[dict, int]]) -> list[BomLineItem]:
    """One shell per container. Reason: primary + feeder grid containers share
    a shell part, so it sums to one line."""
    shells = {
        bom_yaml["shell"]["part_number"]: bom_yaml["shell"] for bom_yaml, _ in boms
    }
    qty = {pn: 0 for pn in shells}
    for bom_yaml, container_qty in boms:
        qty[bom_yaml["shell"]["part_number"]] += container_qty
    return [shell_to_custom_line(shells[pn], q) for pn, q in qty.items()]


def serialize_bom(bom: Bom) -> bytes:
    """Serialize a Bom to JSON bytes for S3 upload."""
    return json.dumps(bom.model_dump(mode="json"), indent=2).encode("utf-8")
