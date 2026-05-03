"""Loads `hardware_selector_map.yaml` at startup; serves profile -> URLs lookups."""

from pathlib import Path

import yaml

from src.hardware_selector.hardware_selector_models import (
    HardwareSelectorMap,
    ProfileAssemblies,
)
from src.shared.enums import DeploymentProfile


class HardwareSelectorService:
    """Profile -> pre-built assembly URLs. Yaml loaded once at __init__."""

    def __init__(self, yaml_path: Path) -> None:
        with yaml_path.open() as f:
            data = yaml.safe_load(f)
        self._map = HardwareSelectorMap.model_validate(data)

    def lookup(self, profile: DeploymentProfile) -> ProfileAssemblies:
        """Return assembly URLs for the given profile. Raises KeyError if missing."""
        return self._map.profiles[profile]
