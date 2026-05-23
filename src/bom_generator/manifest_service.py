"""ManifestService — resolves deployment profile → asset URLs against a Manifest.

Source of truth for assembly + plate URLs is the manifest published to S3
by edp-module-assemblies. JobsService fetches that manifest per-job via
`ManifestClient.fetch_manifest()`, then wraps it in a ManifestService for
the resolve call and pins the underlying Manifest on the JobRecord so the
pipeline sees the same snapshot at DTM emit time (closes ADR-012 torn-read).

`resolve(profile_str)` returns a `ResolvedProfile` containing fully-resolved
URLs — downstream callers (artifact_urls, BOM generator, DTM generator) need
no further manifest navigation.
"""

from dataclasses import dataclass

from src.bom_generator.manifest_models import (
    AssemblyVariant,
    Manifest,
    PlateUrls,
)

# Top-level keys under `Manifest.assemblies` (per edp-module-assemblies schema).
_COMPUTE_ASSEMBLY_KEY = "compute_container"
_GRID_ASSEMBLY_KEY = "grid_container"


@dataclass(frozen=True)
class ResolvedPlate:
    """One plate row — keeps `plate_id` attached for artifact-row labelling."""

    plate_id: str
    urls: PlateUrls


@dataclass(frozen=True)
class ResolvedProfile:
    """Profile lookup output. Fully-resolved URLs; no further manifest work needed."""

    compute: AssemblyVariant
    grid: AssemblyVariant | None  # None when profile.grid_container is None
    plates: list[ResolvedPlate]


class ManifestService:
    """Profile → resolved-URLs lookups against a pinned Manifest snapshot."""

    def __init__(self, manifest: Manifest) -> None:
        self._manifest = manifest

    def resolve(self, profile: str) -> ResolvedProfile:
        """Look up `profile` and resolve every reference inside.

        Raises KeyError if the profile is unknown or any referenced
        assembly/variant/plate is missing — fail fast at order intake rather
        than silently producing partial artifact lists.
        """
        prof = self._manifest.profiles[profile]
        compute = self._manifest.assemblies[_COMPUTE_ASSEMBLY_KEY][
            prof.compute_container
        ]
        grid = (
            self._manifest.assemblies[_GRID_ASSEMBLY_KEY][prof.grid_container]
            if prof.grid_container is not None
            else None
        )
        plates = [
            ResolvedPlate(plate_id=pid, urls=self._manifest.plates[pid])
            for pid in prof.interface_plates
        ]
        return ResolvedProfile(compute=compute, grid=grid, plates=plates)
