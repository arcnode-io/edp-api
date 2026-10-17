"""Budget price list (`pricing.yaml`) — mirror of edp-module-assemblies.

Keyed by equipment id, container shell part number, or plate part number.
Each key holds quantity breaks, lowest `min_qty` first; a line buying
`qty` uses the last break with `min_qty <= qty`.
"""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PriceSource(StrEnum):
    """Where a budget price came from; sets how far to trust it."""

    QUOTE = "quote"  # a vendor's written quote
    DISTRIBUTOR = "distributor"  # a distributor's listed price
    ESTIMATE = "estimate"  # our estimate from public prices of similar gear


class PriceBreak(BaseModel):
    """One unit price from `min_qty` up."""

    model_config = ConfigDict(extra="forbid")

    unit_usd: float = Field(gt=0)
    min_qty: int = Field(default=1, ge=1)
    source: PriceSource
    basis: str  # where the number came from: quote ref, listing, method
    as_of: date


class PriceBook(BaseModel):
    """Every budget price, by part."""

    model_config = ConfigDict(extra="forbid")

    prices: dict[str, list[PriceBreak]] = Field(default_factory=dict)
