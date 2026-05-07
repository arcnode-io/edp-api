"""Output schema for `bom.json` per Q17-A + ADR-009.

Flat line-items with `procurement_path` discriminator. Top-level metadata
block (deployment_id, profile, manifest_version, generated_at).
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


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
