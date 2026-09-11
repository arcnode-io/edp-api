"""GridRegionsConfig — region thresholds + flex-level presets.

Loaded once at startup from config/grid_regions.yaml (single source of truth
for every region-dependent number: distribution limits, DG export caps,
market programs, settlement points, flex-level presets). Region-dependent
validation rules (V4b, V6, SP, FL) key off this; see src/grid/region_validation.py.
"""

from pydantic import BaseModel, ConfigDict

from src.shared.enums import FlexLevel, MarketProgram, MarketRegion


class RegionDefaults(BaseModel):
    """Thresholds that apply across every region (not region-specific)."""

    model_config = ConfigDict(extra="forbid")

    distribution_limit_mw: float
    distribution_near_mw: float


class RegionConfig(BaseModel):
    """Per-ISO/RTO thresholds + what's offered there. Null fields = not yet supported."""

    model_config = ConfigDict(extra="forbid")

    large_load_mw: float | None
    dg_export_max_mw: float | None
    dg_registration_mw: float | None
    market_programs: list[MarketProgram]
    settlement_points: list[str]


class FlexPreset(BaseModel):
    """A named flex-obligation preset — same shape as FlexObligation minus `level`."""

    model_config = ConfigDict(extra="forbid")

    depth_pct: float
    max_duration_h: float
    max_events_yr: int
    min_interval_h: float
    notice_s: int


class GridRegionsConfig(BaseModel):
    """Top-level parse of config/grid_regions.yaml."""

    model_config = ConfigDict(extra="forbid")

    defaults: RegionDefaults
    regions: dict[MarketRegion, RegionConfig]
    flex_levels: dict[FlexLevel, FlexPreset]
