"""Pydantic shape of `hardware_selector_map.yaml`."""

from pydantic import BaseModel

from src.shared.enums import DeploymentProfile


class AssemblyUrls(BaseModel):
    """Pre-built assembly artifact URLs for one container."""

    step: str
    glb: str
    topology_yaml: str  # device topology spec (lives in edp-module-assemblies)


class PlateUrls(BaseModel):
    """Interface plate URLs by format."""

    id: str
    step: str
    dxf: str
    pdf: str


class ProfileAssemblies(BaseModel):
    """All assets for one DeploymentProfile."""

    compute_container: AssemblyUrls
    grid_container: AssemblyUrls | None  # None for *_no_bess profiles
    interface_plates: list[PlateUrls]


class HardwareSelectorMap(BaseModel):
    """Top-level yaml: profile -> ProfileAssemblies."""

    profiles: dict[DeploymentProfile, ProfileAssemblies]
