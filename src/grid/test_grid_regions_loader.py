"""GridRegionsLoader unit tests using tmp_path fixtures."""

from pathlib import Path

import pytest

from src.grid.grid_regions_loader import GridRegionsLoader, GridRegionsLoadError


def test_loads_valid_yaml(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "grid_regions.yaml"
    path.write_text("""
defaults: { distribution_limit_mw: 20, distribution_near_mw: 15 }
regions:
  ercot: { large_load_mw: 75, dg_export_max_mw: 10, dg_registration_mw: 1,
           market_programs: [ercot_ader], settlement_points: [HB_NORTH] }
flex_levels:
  standard: { depth_pct: 50, max_duration_h: 4, max_events_yr: 40, min_interval_h: 20, notice_s: 600 }
""".lstrip())
    loader = GridRegionsLoader(path)

    # Act
    config = loader.load()

    # Assert
    assert config.defaults.distribution_limit_mw == 20


def test_raises_on_missing_file(tmp_path: Path) -> None:
    # Arrange
    loader = GridRegionsLoader(tmp_path / "nonexistent.yaml")

    # Act / Assert
    with pytest.raises(GridRegionsLoadError):
        loader.load()


def test_raises_on_invalid_yaml(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "grid_regions.yaml"
    path.write_text("defaults: : :\n")
    loader = GridRegionsLoader(path)

    # Act / Assert
    with pytest.raises(GridRegionsLoadError, match="invalid YAML"):
        loader.load()


def test_raises_on_schema_violation(tmp_path: Path) -> None:
    # Arrange — missing required `regions` key
    path = tmp_path / "grid_regions.yaml"
    path.write_text(
        "defaults: { distribution_limit_mw: 20, distribution_near_mw: 15 }\n"
        "flex_levels: {}\n"
    )
    loader = GridRegionsLoader(path)

    # Act / Assert
    with pytest.raises(GridRegionsLoadError, match="schema validation failed"):
        loader.load()


def test_loads_real_grid_regions_yaml() -> None:
    """The actual config/grid_regions.yaml shipped in the repo parses clean."""
    # Arrange
    repo_root = Path(__file__).resolve().parents[2]
    loader = GridRegionsLoader(repo_root / "config" / "grid_regions.yaml")

    # Act
    config = loader.load()

    # Assert
    assert config.defaults.distribution_limit_mw == 20
