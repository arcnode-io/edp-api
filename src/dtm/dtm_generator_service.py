"""DtmGeneratorService — emits canonical Dtm per ADR-002 §7."""

from src.bom_generator.manifest_client import ManifestClient
from src.dtm.dtm_generator_internals import (
    collect_templates_used,
    emit_container,
    sizing,
)
from src.shared.schemas.dtm import (
    Bus,
    Device,
    Dtm,
    EmsMode,
)
from src.shared.schemas.module_resolution import ModuleResolution
from src.shared.schemas.template import DeviceTemplate


class DtmGeneratorService:
    """Builds a canonical Dtm. ems-device-api owns later LIVE rewrites."""

    def __init__(
        self,
        manifest_client: ManifestClient,
        template_catalog: dict[str, DeviceTemplate],
    ) -> None:
        self._client = manifest_client
        self._catalog = template_catalog

    def generate(self, *, profile: str, resolution: ModuleResolution) -> Dtm:
        """Compose devices from manifest topology yamls + resolution.

        Args:
            profile: Profile name (e.g. "commercial_ac"). Must exist in manifest.
            resolution: ModuleResolution with deployment_id, container counts,
                gpu_variant/count, bess, etc.

        Returns:
            Dtm in SIM mode with devices, buses, and templates_used populated.

        Raises:
            ValueError: If profile is not in the manifest.
        """
        manifest = self._client.fetch_manifest()
        if profile not in manifest.profiles:
            raise ValueError(
                f"profile {profile!r} not in manifest "
                f"(available: {sorted(manifest.profiles)})"
            )
        prof = manifest.profiles[profile]

        devices: dict[str, Device] = {}
        buses: list[Bus] = []
        slug_counter: dict[str, int] = {}
        by_template: dict[str, list[str]] = {}

        for _ in range(resolution.compute_container_count):
            emit_container(
                client=self._client,
                manifest=manifest,
                asm_type="compute_container",
                variant=prof.compute_container,
                devices=devices,
                buses=buses,
                slug_counter=slug_counter,
                by_template=by_template,
            )

        if prof.grid_container is not None:
            emit_container(
                client=self._client,
                manifest=manifest,
                asm_type="grid_container",
                variant=prof.grid_container,
                devices=devices,
                buses=buses,
                slug_counter=slug_counter,
                by_template=by_template,
            )

        return Dtm(
            deployment_uuid=resolution.deployment_id,
            ems_mode=EmsMode.SIM,
            sizing_params=sizing(resolution),
            devices=devices,
            buses=buses,
            templates_used=collect_templates_used(devices, self._catalog),
        )
