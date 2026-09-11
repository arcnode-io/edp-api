"""Grid participation model — split out of configurator_payload.py (200-line budget).

Site*, OnsiteGeneration, WiresOwner, FlexObligation, Grid + structural validators
(V1-V5a, V7, EX). Region-dependent rules (V4b, V6, SP, FL) need grid_regions.yaml.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.shared.enums import (
    ExportMode,
    FlexLevel,
    GridPath,
    InterconnectionLevel,
    MarketAccess,
    MarketProgram,
    MarketRegion,
    OnsiteGenerationType,
    ServiceType,
    WiresOwnerType,
)


class SiteLocation(BaseModel):
    """Site coordinates — input to platform-api's /grid/resolve."""

    model_config = ConfigDict(extra="forbid")

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    address: str | None = None


class Site(BaseModel):
    """Where the deployment physically sits."""

    model_config = ConfigDict(extra="forbid")

    location: SiteLocation
    country: str  # ISO 3166-1 alpha-2, uppercase, exactly 2 chars
    state: str | None = None

    @field_validator("country")
    @classmethod
    def country_is_iso_alpha2(cls, v: str) -> str:
        """country must be an uppercase 2-letter ISO 3166-1 alpha-2 code."""
        if len(v) != 2 or not v.isalpha() or not v.isupper():
            raise ValueError("country must be an uppercase 2-letter ISO 3166-1 code")
        return v


class OnsiteGeneration(BaseModel):
    """Behind-the-meter generation — independent of grid.path."""

    model_config = ConfigDict(extra="forbid")

    type: OnsiteGenerationType
    capacity_mw: float | None = None

    @model_validator(mode="after")
    def capacity_matches_type(self) -> "OnsiteGeneration":
        """V7: capacity_mw > 0 iff type != none; null iff type == none."""
        if self.type == OnsiteGenerationType.NONE:
            if self.capacity_mw is not None:
                raise ValueError("capacity_mw must be null when type=none")
        elif self.capacity_mw is None or self.capacity_mw <= 0:
            raise ValueError("capacity_mw must be > 0 when type != none")
        return self


class WiresOwner(BaseModel):
    """The utility that owns the wires at the site — from /grid/resolve."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    type: WiresOwnerType
    eia_id: int | None = None


class FlexObligation(BaseModel):
    """Curtailment commitment terms for a flexible/grid_revenue path."""

    model_config = ConfigDict(extra="forbid")

    level: FlexLevel
    depth_pct: float = Field(gt=0, le=100)
    max_duration_h: float = Field(gt=0)
    max_events_yr: int = Field(ge=0)
    min_interval_h: float = Field(gt=0)
    notice_s: int = Field(ge=0)


class Grid(BaseModel):
    """Grid interconnection + market participation. path is the top-level choice."""

    model_config = ConfigDict(extra="forbid")

    path: GridPath
    interconnection_level: InterconnectionLevel | None = None  # server-derived, rule IL
    wires_owner: WiresOwner | None = None
    retail_provider_separate: bool = False
    market_region: MarketRegion | None = None
    service_type: ServiceType | None = None
    flex_obligation: FlexObligation | None = None
    export_mode: ExportMode = ExportMode.NON_EXPORT
    export_limit_mw: float | None = None
    market_access: MarketAccess = MarketAccess.NONE
    market_program: MarketProgram | None = None
    settlement_point: str | None = None
    intentional_islanding: bool = False

    @model_validator(mode="after")
    def off_grid_forces_null_grid_fields(self) -> "Grid":
        """V1: path=off_grid means no grid participation at all."""
        if self.path != GridPath.OFF_GRID:
            return self
        expected: dict[str, tuple[object, object]] = {
            "interconnection_level": (self.interconnection_level, None),
            "wires_owner": (self.wires_owner, None),
            "market_region": (self.market_region, None),
            "service_type": (self.service_type, None),
            "flex_obligation": (self.flex_obligation, None),
            "export_limit_mw": (self.export_limit_mw, None),
            "market_program": (self.market_program, None),
            "settlement_point": (self.settlement_point, None),
            "retail_provider_separate": (self.retail_provider_separate, False),
            "export_mode": (self.export_mode, ExportMode.NON_EXPORT),
            "market_access": (self.market_access, MarketAccess.NONE),
            "intentional_islanding": (self.intentional_islanding, False),
        }
        bad = [k for k, (actual, want) in expected.items() if actual != want]
        if bad:
            raise ValueError(f"path=off_grid requires {bad} to be null/default")
        return self

    @model_validator(mode="after")
    def flexible_or_firm_path_shape(self) -> "Grid":
        """V2/V3: flexible/firm require matching service_type, no export/market program.

        flex_obligation is required for flexible, forbidden for firm; one validator
        since everything else about the two paths is identical.
        """
        is_flex = self.path == GridPath.FLEXIBLE
        if not is_flex and self.path != GridPath.FIRM:
            return self
        want = ServiceType.FLEXIBLE if is_flex else ServiceType.FIRM
        p = self.path.value
        if self.service_type != want:
            raise ValueError(f"path={p} requires service_type={want.value}")
        has_flex = self.flex_obligation is not None
        if is_flex != has_flex:
            raise ValueError(f"path={p} requires flex_obligation set iff flexible")
        if self.export_mode != ExportMode.NON_EXPORT:
            raise ValueError(f"path={p} requires export_mode=non_export")
        if self.market_access != MarketAccess.NONE:
            raise ValueError(f"path={p} requires market_access=none")
        if self.market_program is not None:
            raise ValueError(f"path={p} requires market_program to be null")
        return self

    @model_validator(mode="after")
    def grid_revenue_path_shape(self) -> "Grid":
        """V4a: grid_revenue requires real export/market participation."""
        if self.path != GridPath.GRID_REVENUE:
            return self
        if self.service_type not in (ServiceType.FIRM, ServiceType.FLEXIBLE):
            raise ValueError("grid_revenue requires service_type firm or flexible")
        has_flex = self.flex_obligation is not None
        if (self.service_type == ServiceType.FLEXIBLE) != has_flex:
            raise ValueError("grid_revenue requires flex_obligation iff flexible")
        if self.export_mode == ExportMode.NON_EXPORT:
            raise ValueError("grid_revenue requires export_mode != non_export")
        if self.market_access == MarketAccess.NONE:
            raise ValueError("grid_revenue requires market_access != none")
        if self.market_program is None:
            raise ValueError("grid_revenue requires market_program")
        if self.settlement_point is None:
            raise ValueError("grid_revenue requires settlement_point")
        return self

    @model_validator(mode="after")
    def grid_participation_requires_resolution(self) -> "Grid":
        """V5a: any non-off_grid path requires a resolved utility + market region."""
        if self.path == GridPath.OFF_GRID:
            return self
        if self.wires_owner is None or self.market_region is None:
            raise ValueError("path != off_grid requires wires_owner and market_region")
        return self

    @model_validator(mode="after")
    def export_limit_matches_export_mode(self) -> "Grid":
        """EX: export_limit_mw is set (and > 0) iff export_mode=limited_export."""
        is_limited = self.export_mode == ExportMode.LIMITED_EXPORT
        if is_limited != (self.export_limit_mw is not None):
            raise ValueError("export_limit_mw required iff export_mode=limited_export")
        if self.export_limit_mw is not None and self.export_limit_mw <= 0:
            raise ValueError("export_limit_mw must be > 0")
        return self
