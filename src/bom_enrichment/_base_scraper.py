"""Abstract per-distributor client.

Implementations either drive a B2B portal via Playwright (Graybar,
Anixter, Insight, CDW) or call a REST API (Mouser has a free tier).
Either way, the interface is the same: `fetch_offer(mpn)` returns a
single `DistributorOffer` for the given manufacturer part number.

Concurrency: each scraper instance owns its browser context / API
client and is NOT thread-safe. The orchestrator creates one instance
per distributor and dispatches MPNs sequentially within a distributor;
parallelism happens ACROSS distributors, not within.

Error handling: a network failure / rate limit / selector miss
populates `DistributorOffer.error` rather than raising. The BOM ships
even when one distributor is down (graceful degradation).
"""

from abc import ABC, abstractmethod

from src.bom_enrichment.enrichment_models import DistributorId, DistributorOffer


class DistributorClient(ABC):
    """One implementation per distributor."""

    @property
    @abstractmethod
    def distributor_id(self) -> DistributorId:
        """Stable identifier used in DistributorOffer.distributor."""

    @abstractmethod
    def fetch_offer(self, mpn: str) -> DistributorOffer:
        """Fetch the offer for one MPN. NEVER raises — returns error inside."""

    @abstractmethod
    def close(self) -> None:
        """Release browser / API resources. Subclasses MUST implement (even as no-op)."""
