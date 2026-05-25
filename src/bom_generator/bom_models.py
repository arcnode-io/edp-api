"""Output schema for `bom.json` per Q17-A + ADR-009.

Flat line-items with `procurement_path` discriminator. Top-level metadata
block (deployment_id, profile, manifest_version, generated_at).
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from src.bom_enrichment.enrichment_models import DistributorOffer


class ProcurementPath(StrEnum):
    """Where each line item is sourced."""

    CATALOG = "catalog"
    CUSTOM_FABRICATION = "custom_fabrication"


class BomLineItem(BaseModel):
    """One BOM row. Fields beyond core are optional/path-specific."""

    part_number: str
    vendor: str
    description: str
    qty: int
    procurement_path: ProcurementPath

    # Catalog-only fields
    datasheet_url: str | None = None
    lead_time_weeks: int | None = None
    unit_cost_usd: float | None = None
    fab_tier: str | None = None

    # Track-A enrichment: static fields curated in equipment/<id>/spec.yaml.
    install_video_url: str | None = None  # vendor's published install / unboxing video
    ndaa_compliant: bool | None = None  # NDAA Section 889 — None = unasserted
    taa_compliant: bool | None = None  # Trade Agreements Act — None = unasserted

    # Track-B enrichment: per-distributor offers fetched at BOM generation
    # time. Empty when no enrichment ran (e.g. credentials missing) or when
    # no distributor returned a non-error offer for this MPN.
    offers: list[DistributorOffer] = Field(default_factory=list)

    # Percent change between cheapest current offer and its nearest history
    # snapshot ≥ 7 days old. None when no prior snapshot exists (first-ever
    # scrape or no historical data for this MPN). Positive = price up.
    price_change_pct_7d: float | None = None

    # Custom-fab-only fields
    material: str | None = None
    finish: str | None = None
    drawing_ref: str | None = None
    drawing_url: str | None = None


class Bom(BaseModel):
    """Top-level bom.json output."""

    deployment_id: UUID
    profile: str
    manifest_version: str
    generated_at: datetime
    compute_container_qty: int
    grid_container_qty: int
    line_items: list[BomLineItem] = Field(default_factory=list)
