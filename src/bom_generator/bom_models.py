"""Output schema for `bom.json` per Q17-A + ADR-009.

Flat line-items with `procurement_path` discriminator. Top-level metadata
block (deployment_id, profile, manifest_version, generated_at).
"""

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, computed_field

from src.bom_enrichment.enrichment_models import DistributorOffer
from src.bom_generator.pricing_models import PriceSource


class ProcurementPath(StrEnum):
    """How each line item is sourced."""

    CATALOG = "catalog"  # bought by manufacturer part number
    ENGINEERED_TO_ORDER = "engineered_to_order"  # built to our spec, by RFQ
    CUSTOM_FABRICATION = "custom_fabrication"  # cut by a shop to ARCNODE drawings
    CUSTOMER_SUPPLIED = "customer_supplied"  # the customer's own equipment
    BY_OTHERS = "by_others"  # site work by the customer's contractors
    FIELD_SUPPLIED = "field_supplied"  # bulk material the installer provides


class BomSection(StrEnum):
    """Where in the deployment a line sits; the BOM is grouped in this order."""

    COMPUTE = "compute_container"
    GRID = "grid_container"
    SITE = "site_and_interfaces"
    FIELD = "field_install"


_SUPPLIER: dict[ProcurementPath, str] = {
    ProcurementPath.BY_OTHERS: "By others",
    ProcurementPath.FIELD_SUPPLIED: "Installer",
}


class BomOrder(BaseModel):
    """The order as placed and as delivered — the BOM header."""

    customer: str
    site: str
    deployment_context: str
    gpu_variant: str
    gpus_requested: int
    gpus_delivered: int  # whole servers of 8 GPUs
    bess_capacity_mwh: float
    bess_coupling: str
    pcs_qty: int  # dc_ext PCS sized to the battery's job, else 0


class BomLineItem(BaseModel):
    """One BOM row. Fields beyond core are optional/path-specific."""

    item: int = 0  # 1-based, assigned when the BOM is finalized
    section: BomSection
    ref_des: str  # device tags this line covers, e.g. "C1-C2: NODE-1…7"
    part_number: str
    vendor: str
    description: str
    qty: int
    uom: str = "ea"
    procurement_path: ProcurementPath
    notes: str = ""

    # Catalog-only fields
    equipment_id: str | None = None  # edp-module-assemblies equipment/<id>
    datasheet_url: str | None = None
    lead_time_weeks: int | None = None
    # The price used: live distributor offer, else the budget price list
    unit_cost_usd: float | None = None
    price_source: PriceSource | None = None
    price_basis: str | None = None  # distributor, quote ref or estimate method
    price_as_of: date | None = None
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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def supplied_by(self) -> str:
        """Customer, By others or Installer — from the procurement path.

        ARCNODE sells software only; the customer buys or already owns
        everything not left to their contractors or installer.
        """
        return _SUPPLIER.get(self.procurement_path, "Customer")


class BomBudget(BaseModel):
    """Budgetary total of the parts the customer buys. Not a quote."""

    total_usd: float
    low_usd: float  # each priced line less its source's band
    high_usd: float
    quote_backed_pct: float  # share of total dollars from vendor quotes
    unpriced_lines: int  # bought lines with no price, not in the total


class Bom(BaseModel):
    """Top-level bom.json output."""

    deployment_id: UUID
    profile: str
    manifest_version: str
    generated_at: datetime
    compute_container_qty: int
    grid_container_qty: int
    order: BomOrder
    line_items: list[BomLineItem] = Field(default_factory=list)
    budget: BomBudget | None = None  # set once line prices are final
