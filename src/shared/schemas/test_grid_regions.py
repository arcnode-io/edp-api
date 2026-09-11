"""GridRegionsConfig schema unit tests."""

from src.shared.enums import FlexLevel, MarketProgram, MarketRegion
from src.shared.schemas.grid_regions import GridRegionsConfig


def _raw() -> dict[str, object]:
    return {
        "defaults": {"distribution_limit_mw": 20, "distribution_near_mw": 15},
        "regions": {
            "ercot": {
                "large_load_mw": 75,
                "dg_export_max_mw": 10,
                "dg_registration_mw": 1,
                "market_programs": ["ercot_ader", "ercot_dgr"],
                "settlement_points": ["HB_NORTH"],
            },
            "caiso": {
                "large_load_mw": None,
                "dg_export_max_mw": None,
                "dg_registration_mw": None,
                "market_programs": [],
                "settlement_points": [],
            },
        },
        "flex_levels": {
            "standard": {
                "depth_pct": 50,
                "max_duration_h": 4,
                "max_events_yr": 40,
                "min_interval_h": 20,
                "notice_s": 600,
            },
        },
    }


def test_parses_defaults() -> None:
    # Arrange / Act
    config = GridRegionsConfig.model_validate(_raw())
    # Assert
    assert config.defaults.distribution_limit_mw == 20
    assert config.defaults.distribution_near_mw == 15


def test_parses_region_by_enum_key() -> None:
    # Arrange / Act
    config = GridRegionsConfig.model_validate(_raw())
    # Assert
    ercot = config.regions[MarketRegion.ERCOT]
    assert ercot.large_load_mw == 75
    assert ercot.market_programs == [MarketProgram.ERCOT_ADER, MarketProgram.ERCOT_DGR]
    assert ercot.settlement_points == ["HB_NORTH"]


def test_parses_region_with_null_thresholds() -> None:
    # Arrange / Act
    config = GridRegionsConfig.model_validate(_raw())
    # Assert
    caiso = config.regions[MarketRegion.CAISO]
    assert caiso.large_load_mw is None
    assert caiso.market_programs == []


def test_parses_flex_preset_by_enum_key() -> None:
    # Arrange / Act
    config = GridRegionsConfig.model_validate(_raw())
    # Assert
    standard = config.flex_levels[FlexLevel.STANDARD]
    assert standard.depth_pct == 50
    assert standard.max_events_yr == 40


def test_loads_real_grid_regions_yaml() -> None:
    """The actual config/grid_regions.yaml parses clean."""
    # Arrange
    import yaml
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    raw = yaml.safe_load((repo_root / "config" / "grid_regions.yaml").read_text())

    # Act
    config = GridRegionsConfig.model_validate(raw)

    # Assert — all 8 market regions present, ercot has real thresholds
    assert set(config.regions.keys()) == set(MarketRegion)
    assert config.regions[MarketRegion.ERCOT].dg_export_max_mw == 10
    assert set(config.flex_levels.keys()) == {
        FlexLevel.LIGHT,
        FlexLevel.STANDARD,
        FlexLevel.HEAVY,
    }
