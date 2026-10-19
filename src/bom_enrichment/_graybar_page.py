"""Reading a Graybar product detail page into an offer.

Split out of _graybar_client.py (200-line budget).
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.bom_enrichment.enrichment_models import DistributorId, DistributorOffer

if TYPE_CHECKING:
    from playwright.sync_api import Page


def parse_product_detail(page: "Page", mpn: str) -> DistributorOffer:
    """Read MPN + price + availability from the loaded product detail page.

    Graybar exposes everything we need as `data-*` attributes on the
    product container — far more stable than CSS-class scraping. The
    `.availability` text block carries stock state ("In Stock" / "Out
    of Stock to Ship") that we map to `stock_count` 1 / 0. Real
    per-distributor stock counts aren't shown to logged-in users at
    v1; Graybar surfaces "in stock at branch" / "out of stock" only.

    Sets `error` to "ambiguous match" when the page's `data-mpn`
    doesn't include the queried MPN — search relevance is fuzzy.
    """
    data = page.evaluate("""
        () => {
            const el = document.querySelector('[data-mpn]');
            if (!el) return {};
            return {
                mpn: el.getAttribute('data-mpn'),
                sku: el.getAttribute('data-sku'),
                price: el.getAttribute('data-price'),
                manufacturer: el.getAttribute('data-manufacturer'),
            };
        }
        """)
    availability_text = _text_or_none(page, ".availability") or ""
    in_stock = (
        "In Stock" in availability_text and "Out of Stock" not in availability_text
    )

    page_mpn = (data.get("mpn") or "").strip()
    ambiguous = (
        mpn.upper() not in page_mpn.upper() and page_mpn.upper() not in mpn.upper()
    )

    return DistributorOffer(
        distributor="graybar",
        mpn=mpn,
        stock_count=1 if in_stock else 0,
        lead_time_weeks=None,  # Graybar doesn't surface lead-time on PDP at v1
        unit_cost_usd=_safe_float(data.get("price")),
        refreshed_at=datetime.now(UTC),
        error=(
            f"ambiguous match: search returned MPN {page_mpn!r}" if ambiguous else None
        ),
    )


def error_offer(distributor: DistributorId, mpn: str, message: str) -> DistributorOffer:
    """Build an error-only offer for fetches that failed before extraction."""
    return DistributorOffer(
        distributor=distributor,
        mpn=mpn,
        refreshed_at=datetime.now(UTC),
        error=message,
    )


def _text_or_none(page: "Page", selector: str) -> str | None:
    """Return `selector`'s text content; None if selector missing or invisible."""
    el = page.query_selector(selector)
    if el is None:
        return None
    return el.inner_text().strip()


def _safe_float(s: str | None) -> float | None:
    """Parse `s` as float, stripping $ and commas. None if unparseable."""
    if s is None:
        return None
    cleaned = s.replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None
