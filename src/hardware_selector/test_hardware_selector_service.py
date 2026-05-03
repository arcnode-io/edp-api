"""HardwareSelectorService unit tests. Loads the real top-level yaml."""

from pathlib import Path

import pytest

from src.hardware_selector.hardware_selector_models import ProfileAssemblies
from src.hardware_selector.hardware_selector_service import HardwareSelectorService
from src.shared.enums import DeploymentProfile

YAML_PATH: Path = Path(__file__).resolve().parents[2] / "hardware_selector_map.yaml"


def test_loads_all_11_valid_profiles() -> None:
    """All 11 DeploymentProfile enum values resolve."""
    # Arrange
    service = HardwareSelectorService(yaml_path=YAML_PATH)

    # Act / Assert
    for profile in DeploymentProfile:
        assert isinstance(service.lookup(profile), ProfileAssemblies), profile


def test_commercial_ac_returns_expected_compute_url() -> None:
    """Spot-check one profile's compute_container.step URL."""
    # Arrange
    service = HardwareSelectorService(yaml_path=YAML_PATH)

    # Act
    actual = service.lookup(DeploymentProfile.COMMERCIAL_AC)

    # Assert
    assert (
        actual.compute_container.step
        == "s3://arcnode-artifacts/assemblies/compute-container/commercial-ac/assembly.step"
    )


def test_no_bess_has_null_grid_container() -> None:
    """*_no_bess profiles omit grid_container."""
    # Arrange
    service = HardwareSelectorService(yaml_path=YAML_PATH)

    # Act
    actual = service.lookup(DeploymentProfile.COMMERCIAL_NO_BESS)

    # Assert
    assert actual.grid_container is None


def test_ac_profile_includes_bg_ac_plate() -> None:
    """AC-coupled profiles ship the BG-AC interface plate."""
    # Arrange
    service = HardwareSelectorService(yaml_path=YAML_PATH)

    # Act
    actual = service.lookup(DeploymentProfile.COMMERCIAL_AC)

    # Assert
    plate_ids = {p.id for p in actual.interface_plates}
    assert "BG-AC" in plate_ids


def test_dc_profile_includes_bg_dc_plate() -> None:
    """DC profiles ship the BG-DC interface plate (not BG-AC)."""
    # Arrange
    service = HardwareSelectorService(yaml_path=YAML_PATH)

    # Act
    actual = service.lookup(DeploymentProfile.FEDERAL_DC_EXT)

    # Assert
    plate_ids = {p.id for p in actual.interface_plates}
    assert "BG-DC" in plate_ids
    assert "BG-AC" not in plate_ids


def test_topology_yaml_url_present_on_compute_container() -> None:
    """Every compute_container has a topology_yaml URL."""
    # Arrange
    service = HardwareSelectorService(yaml_path=YAML_PATH)

    # Act / Assert
    for profile in DeploymentProfile:
        assert service.lookup(profile).compute_container.topology_yaml.startswith(
            "s3://"
        ), profile


def test_unknown_profile_raises() -> None:
    """Defensive: a string not in the enum can't be looked up."""
    # Arrange
    service = HardwareSelectorService(yaml_path=YAML_PATH)

    # Act / Assert
    with pytest.raises(KeyError):
        service.lookup("not_a_profile")  # ty: ignore[invalid-argument-type]
