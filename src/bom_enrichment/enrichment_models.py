"""Enrichment data shapes — what one distributor reports about one MPN.

Each per-distributor client returns 0..1 `DistributorOffer` per MPN per call.
The orchestrator aggregates across distributors into `EnrichmentForMpn`,
which the BOM generator merges back into `BomLineItem` (the cheapest offer
wins on `unit_cost_usd`; lead time + stock surface per-distributor for
buyer comparison).

Errors are first-class — a per-distributor failure (login broken, MPN
not in catalog, rate-limited, portal redesign) populates `error` so the
caller can choose to retry / fall back / show graceful UI.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

# Distributor identifiers — keep enum-shaped so per-distributor lookup is exact.
DistributorId = Literal["graybar", "anixter", "insight", "mouser", "cdw"]

LifecycleStatus = Literal[
    "active",  # available, no EOL announced
    "nrnd",  # not recommended for new designs
    "eol_announced",  # EOL date published, still available
    "discontinued",  # past EOL, no new stock
]


class DistributorOffer(BaseModel):
    """One distributor's offer for one MPN, as observed at refresh time."""

    model_config = ConfigDict(extra="forbid")

    distributor: DistributorId
    mpn: str
    stock_count: int | None = None  # None = unknown; 0 = explicit out-of-stock
    lead_time_weeks: int | None = None
    unit_cost_usd: float | None = None  # spot price at qty=1
    lifecycle_status: LifecycleStatus | None = None
    eol_date: date | None = None
    refreshed_at: datetime
    error: str | None = None  # populated when scrape/API failed; offer is partial


class EnrichmentForMpn(BaseModel):
    """All distributors' offers for one MPN — merged downstream into BomLineItem."""

    model_config = ConfigDict(extra="forbid")

    mpn: str
    offers: list[DistributorOffer]
    refreshed_at: datetime
