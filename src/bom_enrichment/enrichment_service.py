"""EnrichmentService — orchestrates per-distributor clients across an MPN list.

Each `DistributorClient` is queried in parallel (one thread per
distributor); within a distributor, MPNs are queried sequentially to
respect per-portal rate limits + share a single authenticated session.

Returns `dict[mpn, EnrichmentForMpn]`. A distributor whose client
errored out still contributes an offer with `error` populated, so the
caller knows whether the missing data is "out of catalog" vs "scrape
broken".

Wired into the BOM pipeline at v1 by calling
`EnrichmentService.enrich(mpns)` after the BOM is built, then merging
`unit_cost_usd` / `lead_time_weeks` from the cheapest offer into each
`BomLineItem`. Pipeline emits both the merged BOM and the full
per-distributor enrichment data as a sibling JSON artifact.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from src.bom_enrichment._base_scraper import DistributorClient
from src.bom_enrichment._offer_cache import OfferCache
from src.bom_enrichment._offer_history import OfferHistory, compute_delta_pct
from src.bom_enrichment.enrichment_models import (
    DistributorOffer,
    EnrichmentForMpn,
)

logger = logging.getLogger(__name__)


class EnrichmentService:
    """Drives a fixed set of DistributorClients to enrich a list of MPNs."""

    def __init__(
        self,
        clients: list[DistributorClient],
        *,
        cache: OfferCache | None = None,
        history: OfferHistory | None = None,
    ) -> None:
        self._clients = clients
        self._cache = cache
        self._history = history

    def enrich(self, mpns: list[str]) -> dict[str, EnrichmentForMpn]:
        """Fetch offers for every MPN from every client. Parallel per client.

        Returns one `EnrichmentForMpn` per input MPN. Order is NOT preserved;
        caller indexes by MPN.
        """
        # One thread per client — each client serializes its own MPN list to
        # respect rate limits and share its authenticated session.
        with ThreadPoolExecutor(max_workers=max(len(self._clients), 1)) as pool:
            per_client_results = list(
                pool.map(
                    lambda client: _fetch_all_for_client(
                        client, mpns, self._cache, self._history
                    ),
                    self._clients,
                )
            )

        # Pivot: dict[mpn][distributor_id] = offer.
        offers_by_mpn: dict[str, list[DistributorOffer]] = {mpn: [] for mpn in mpns}
        for client_offers in per_client_results:
            for offer in client_offers:
                offers_by_mpn[offer.mpn].append(offer)

        now = datetime.now(UTC)
        return {
            mpn: EnrichmentForMpn(mpn=mpn, offers=offers, refreshed_at=now)
            for mpn, offers in offers_by_mpn.items()
        }

    def price_delta_pct_7d(self, offer: DistributorOffer) -> float | None:
        """% change between this offer's price and its nearest 7-day-old snapshot.

        Returns None when no history backend is configured, the offer is
        an error, or no qualifying snapshot exists.
        """
        if self._history is None or offer.error is not None:
            return None
        snaps = self._history.list_snapshots(
            distributor=offer.distributor, mpn=offer.mpn
        )
        return compute_delta_pct(current=offer, snapshots=snaps, now=offer.refreshed_at)

    def close(self) -> None:
        """Release browser / API resources across all clients."""
        for client in self._clients:
            try:
                client.close()
            except Exception:
                # Reason: best-effort cleanup; one bad client shouldn't block
                # the rest. Log + continue.
                logger.exception("client %s close raised", client.distributor_id)


def _fetch_all_for_client(
    client: DistributorClient,
    mpns: list[str],
    cache: OfferCache | None,
    history: OfferHistory | None,
) -> list[DistributorOffer]:
    """Sequential per-distributor — share session, respect rate limit.

    Cache lookup short-circuits the scrape when a fresh offer exists.
    Successful scrapes are written to cache + history; error offers are
    skipped in both stores.
    """
    results: list[DistributorOffer] = []
    for mpn in mpns:
        if cache is not None:
            cached = cache.get(distributor=client.distributor_id, mpn=mpn)
            if cached is not None:
                results.append(cached)
                continue
        try:
            offer = client.fetch_offer(mpn)
        except Exception as e:
            # Reason: clients SHOULD catch + populate error inside DistributorOffer.
            # This is the safety net for truly unexpected exceptions.
            logger.exception(
                "client %s unexpectedly raised on %s", client.distributor_id, mpn
            )
            offer = DistributorOffer(
                distributor=client.distributor_id,
                mpn=mpn,
                refreshed_at=datetime.now(UTC),
                error=f"unexpected: {e!r}",
            )
        if cache is not None:
            cache.put(offer)
        if history is not None:
            history.record(offer)
        results.append(offer)
    return results
