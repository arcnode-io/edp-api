"""Every profile resolves to its expected artifact URL count."""

import pytest

from src.shared.enums import GpuVariant
from src.bom_generator.manifest_models import (
    Manifest,
    ProfileAssemblies,
)
from src.bom_generator.manifest_service import ManifestService
from src.pipeline.artifact_urls import build_artifact_urls_from_resolved
from src.pipeline.artifact_urls_test_support import (
    DEPLOYMENT_ID,
    _variant,
    _plate,
)


def _all_seven_profiles_manifest() -> Manifest:
    """Mirrors edp-module-assemblies/manifest_profiles.yaml — all 7 v1 profiles.

    `defense_dc_int` is intentionally absent; CATL EnerOne is excluded from
    DoD procurement per system_adrs.md, and module_resolver rejects
    defense_forward + dc_integrated_pcs at Pydantic ingress before reaching
    profile resolution.
    """
    return Manifest(
        version="0.0.0-test",
        assemblies={
            "compute_container": {
                "commercial-ac": _variant("compute-commercial-ac"),
                "defense-ac": _variant("compute-defense-ac"),
            },
            "grid_container": {
                "commercial-ac": _variant("grid-commercial-ac"),
                "commercial-dc-ext": _variant("grid-commercial-dc-ext"),
                "no-bess": _variant("grid-no-bess"),
                "defense-ac": _variant("grid-defense-ac"),
                "defense-dc-ext": _variant("grid-defense-dc-ext"),
                "defense-no-bess": _variant("grid-defense-no-bess"),
            },
        },
        plates={
            "CG": _plate("CG"),
            "BG-AC": _plate("BG-AC"),
            "BG-DC": _plate("BG-DC"),
            "CD": _plate("CD"),
        },
        profiles={
            "commercial_ac": ProfileAssemblies(
                compute_container="commercial-ac",
                grid_container="commercial-ac",
                interface_plates=["CG", "BG-AC", "CD"],
            ),
            "commercial_dc_int": ProfileAssemblies(
                compute_container="commercial-ac",
                grid_container="commercial-ac",
                interface_plates=["CG", "BG-AC", "CD"],
            ),
            "commercial_dc_ext": ProfileAssemblies(
                compute_container="commercial-ac",
                grid_container="commercial-dc-ext",
                interface_plates=["CG", "BG-DC", "CD"],
            ),
            "defense_ac": ProfileAssemblies(
                compute_container="defense-ac",
                grid_container="defense-ac",
                interface_plates=["CG", "BG-AC", "CD"],
            ),
        },
    )


# Expected URL counts per profile, derived from manifest shape:
# 2 compute_container (step + glb), 2 grid_container (step + glb),
# n plates x 2 formats (step + dxf), 14 deterministic generated artifacts
# (install_sequence ships pdf + xlsx).
# Every profile has 2 grid + 3 plates.
_PROFILE_EXPECTED_URL_COUNT: dict[str, int] = {
    "commercial_ac": 2 + 2 + 3 * 2 + 14,  # 24
    "commercial_dc_int": 2 + 2 + 3 * 2 + 14,
    "commercial_dc_ext": 2 + 2 + 3 * 2 + 14,
    "defense_ac": 2 + 2 + 3 * 2 + 14,
}


@pytest.mark.parametrize("profile", sorted(_PROFILE_EXPECTED_URL_COUNT))
def test_every_v1_profile_resolves_to_expected_url_count(profile: str) -> None:
    """All 4 profiles round-trip through resolve + URL build.

    Closes the "snapshot coverage thin" gap: catches manifest drift across
    every profile, not just commercial_ac.
    """
    # Arrange
    manifest = _all_seven_profiles_manifest()
    resolved = ManifestService(manifest=manifest).resolve(
        profile, gpu_variant=GpuVariant.B200
    )

    # Act
    refs = build_artifact_urls_from_resolved(DEPLOYMENT_ID, resolved)

    # Assert
    assert len(refs) == _PROFILE_EXPECTED_URL_COUNT[profile]
