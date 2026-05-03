"""DI wiring for hardware_selector."""

from pathlib import Path

from src.hardware_selector.hardware_selector_service import HardwareSelectorService

YAML_PATH: Path = Path(__file__).resolve().parents[2] / "hardware_selector_map.yaml"


class HardwareSelectorModule:
    """Loads the top-level yaml at startup; exposes the service."""

    def __init__(self) -> None:
        self.service = HardwareSelectorService(yaml_path=YAML_PATH)
