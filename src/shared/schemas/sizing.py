"""Sizing preview request/response shapes — POST /edp-api/sizing/preview.

`SizingGridInput` is deliberately narrower than the full `Grid` model: a
preview can run before the customer has resolved a utility or committed to
every grid field, so every field here is optional. `SizingFlagCode`/`Level`
are scoped to this endpoint (not in shared enums.py — nothing else uses them).
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from src.shared.enums import (
    BessCoupling,
    DeploymentContext,
    ExportMode,
    GpuVariant,
    GridPath,
    InterconnectionLevel,
    MarketRegion,
    ServiceType,
)
from src.shared.schemas.configurator_grid import FlexObligation, OnsiteGeneration


class LimitState(StrEnum):
    """Where grid_peak_mw sits relative to the distribution thresholds."""

    WITHIN = "within"
    NEAR = "near"
    OVER = "over"


class SizingFlagLevel(StrEnum):
    """Severity of an operator-facing sizing flag."""

    INFO = "info"
    WARN = "warn"


class SizingFlagCode(StrEnum):
    """§5.5 — the flag's identity; SizingFlag.message carries the operator text."""

    TRANSMISSION_MANUAL_ENGAGEMENT = "TRANSMISSION_MANUAL_ENGAGEMENT"
    NEAR_DISTRIBUTION_LIMIT = "NEAR_DISTRIBUTION_LIMIT"
    FLEX_BESS_SHORTFALL = "FLEX_BESS_SHORTFALL"
    RESERVE_SHORTFALL = "RESERVE_SHORTFALL"
    FLEX_NO_BESS = "FLEX_NO_BESS"
    RECHARGE_HEADROOM = "RECHARGE_HEADROOM"
    EXPORT_REVIEW = "EXPORT_REVIEW"
    EXPORT_PCS_RATING_UNVERIFIED = "EXPORT_PCS_RATING_UNVERIFIED"
    NON_EXPORT_TRANSIENT_UNVERIFIED = "NON_EXPORT_TRANSIENT_UNVERIFIED"
    ISLANDING_REVIEW_REQUIRED = "ISLANDING_REVIEW_REQUIRED"
    ISLANDING_TRANSFER_UNVERIFIED = "ISLANDING_TRANSFER_UNVERIFIED"


class SizingFlag(BaseModel):
    """One operator-facing flag on a sizing preview."""

    model_config = ConfigDict(extra="forbid")

    code: SizingFlagCode
    level: SizingFlagLevel
    message: str


class SizingGridInput(BaseModel):
    """Partial grid info for a preview — every field optional/defaulted."""

    model_config = ConfigDict(extra="forbid")

    path: GridPath | None = None
    market_region: MarketRegion | None = None
    service_type: ServiceType | None = None
    flex_obligation: FlexObligation | None = None
    export_mode: ExportMode | None = None
    intentional_islanding: bool = False


class SizingPreviewRequest(BaseModel):
    """POST /edp-api/sizing/preview body."""

    model_config = ConfigDict(extra="forbid")

    gpu_variant: GpuVariant
    target_gpu_count: int = Field(ge=1)
    bess_coupling: BessCoupling
    bess_capacity_mwh: float = Field(ge=0)
    ride_through_hours: float = Field(ge=0, default=0)
    deployment_context: DeploymentContext
    onsite_generation: OnsiteGeneration
    grid: SizingGridInput = Field(default_factory=SizingGridInput)


class SizingLimits(BaseModel):
    """D13 — the three thresholds, so the site-peak range bar needs no second call."""

    model_config = ConfigDict(extra="forbid")

    distribution_limit_mw: float
    distribution_near_mw: float
    large_load_mw: float | None


class FlexPreview(BaseModel):
    """Present iff effective service_type == flexible."""

    model_config = ConfigDict(extra="forbid")

    e_flex_mwh: float
    e_min_usable_mwh: float
    p_contract_mw: float
    p_recharge_mw: float
    bess_covers_h: float
    gpu_cap_pct_during_shortfall: float | None


class SizingPreview(BaseModel):
    """POST /edp-api/sizing/preview response. Also persisted on JobRecord."""

    model_config = ConfigDict(extra="forbid")

    site_peak_mw: float
    firm_onsite_mw: float
    grid_peak_mw: float
    e_reserve_mwh: float
    bess_min_mwh: float
    interconnection_level: InterconnectionLevel
    limit_state: LimitState
    limits: SizingLimits
    recommended_path: GridPath | None
    recommended_reason: str
    flex: FlexPreview | None
    flags: list[SizingFlag]
