"""Pydantic models for `manifest.yaml` consumed from edp-module-assemblies.

Mirrors the schema in edp-module-assemblies/src/manifest_models.py per
ADR-006 + ADR-009. v1 keeps these duplicated in both repos; future work
extracts into a shared `arcnode-contracts` package.
"""

from src.shared.enums import GpuVariant
from pydantic import BaseModel, Field


class GeometryUrls(BaseModel):
    """Per-equipment geometry URLs."""

    envelope: str
    vendor_step: str | None = None


class AssemblyVariant(BaseModel):
    """Per-variant assembly artifact URLs."""

    bom: str
    step: str
    glb: str
    glb_exploded: str | None = None
    step_exploded: str | None = None
    topology_yaml: str | None = None


class PlateUrls(BaseModel):
    """Per-plate-id artifact URLs."""

    spec: str
    step: str
    dxf: str | None = None
    drawing_meta: str | None = None


class ProfileAssemblies(BaseModel):
    """Profile→asset selection. References ids/keys defined elsewhere."""

    compute_container: str
    # GPU type → compute container variant (an H100 order gets H100 nodes).
    # Empty only on manifests published before per-GPU variants existed.
    compute_container_by_gpu: dict[GpuVariant, str] = Field(default_factory=dict)
    grid_container: str | None
    grid_feeder_container: str | None = None  # primary minus the POI meter
    interface_plates: list[str] = Field(default_factory=list)

    def compute_variant(self, gpu_variant: GpuVariant) -> str:
        """Compute container variant for the ordered GPU type.

        Raises:
            KeyError: If the profile maps GPU types but not this one — never
                fall back to another GPU's container.
        """
        if not self.compute_container_by_gpu:
            return self.compute_container
        return self.compute_container_by_gpu[gpu_variant]


class Manifest(BaseModel):
    """Top-level manifest schema (mirror of edp-module-assemblies)."""

    version: str
    specs: dict[str, str] = Field(default_factory=dict)
    geometry: dict[str, GeometryUrls] = Field(default_factory=dict)
    assemblies: dict[str, dict[str, AssemblyVariant]] = Field(default_factory=dict)
    plates: dict[str, PlateUrls] = Field(default_factory=dict)
    profiles: dict[str, ProfileAssemblies] = Field(default_factory=dict)
    pricing: str | None = None  # budget price list (pricing_models.PriceBook)
