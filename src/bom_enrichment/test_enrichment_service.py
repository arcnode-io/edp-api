"""EnrichmentService unit tests with in-memory mock distributor clients.

Real per-distributor scrapers are tested separately via live-portal
integration tests (slow + network-dependent). These tests prove the
orchestration layer: parallel-per-client, sequential-per-MPN, error
isolation, result pivoting by MPN.
"""

from datetime import UTC, datetime

from src.bom_enrichment._base_scraper import DistributorClient
from src.bom_enrichment.enrichment_models import DistributorId, DistributorOffer
from src.bom_enrichment.enrichment_service import EnrichmentService


class _MockClient(DistributorClient):
    """In-memory client returning canned offers per MPN."""

    def __init__(
        self, distributor_id: DistributorId, offers: dict[str, DistributorOffer]
    ) -> None:
        self._distributor_id = distributor_id
        self._offers = offers
        self.close_calls = 0

    @property
    def distributor_id(self) -> DistributorId:
        return self._distributor_id

    def fetch_offer(self, mpn: str) -> DistributorOffer:
        if mpn in self._offers:
            return self._offers[mpn]
        return DistributorOffer(
            distributor=self._distributor_id,
            mpn=mpn,
            refreshed_at=datetime.now(UTC),
            error="not in catalog",
        )

    def close(self) -> None:
        self.close_calls += 1


def _offer(distributor: DistributorId, mpn: str, **kwargs) -> DistributorOffer:  # type: ignore[no-untyped-def]
    return DistributorOffer(
        distributor=distributor,
        mpn=mpn,
        refreshed_at=datetime.now(UTC),
        **kwargs,
    )


def test_enrich_returns_one_entry_per_input_mpn() -> None:
    """Every input MPN appears in the result dict."""
    # Arrange
    client = _MockClient(
        "mouser",
        {"PN-1": _offer("mouser", "PN-1", stock_count=42)},
    )
    service = EnrichmentService([client])

    # Act
    actual = service.enrich(["PN-1", "PN-2"])

    # Assert — both MPNs present; PN-2 has an error-offer (not in catalog)
    assert set(actual) == {"PN-1", "PN-2"}
    assert actual["PN-1"].offers[0].stock_count == 42
    assert actual["PN-2"].offers[0].error == "not in catalog"


def test_enrich_aggregates_offers_across_distributors() -> None:
    """Multiple clients → multiple offers per MPN, one per distributor."""
    # Arrange
    mouser = _MockClient(
        "mouser", {"PN-1": _offer("mouser", "PN-1", unit_cost_usd=10.0)}
    )
    graybar = _MockClient(
        "graybar", {"PN-1": _offer("graybar", "PN-1", unit_cost_usd=12.0)}
    )
    service = EnrichmentService([mouser, graybar])

    # Act
    actual = service.enrich(["PN-1"])

    # Assert
    offers_by_dist = {o.distributor: o for o in actual["PN-1"].offers}
    assert offers_by_dist["mouser"].unit_cost_usd == 10.0
    assert offers_by_dist["graybar"].unit_cost_usd == 12.0


def test_client_raising_unexpectedly_is_isolated_to_its_distributor() -> None:
    """An exception from one client's fetch becomes an error-offer, doesn't kill the run."""

    # Arrange
    class _BrokenClient(DistributorClient):
        @property
        def distributor_id(self) -> DistributorId:
            return "anixter"

        def fetch_offer(self, mpn: str) -> DistributorOffer:
            raise RuntimeError("portal selectors moved")

        def close(self) -> None:
            pass

    working = _MockClient("mouser", {"PN-1": _offer("mouser", "PN-1", stock_count=5)})
    service = EnrichmentService([working, _BrokenClient()])

    # Act
    actual = service.enrich(["PN-1"])

    # Assert — both distributors present; anixter's offer has the error
    by_dist = {o.distributor: o for o in actual["PN-1"].offers}
    assert by_dist["mouser"].stock_count == 5
    assert by_dist["anixter"].error is not None
    assert "selectors" in by_dist["anixter"].error


def test_cached_offer_short_circuits_client_call() -> None:
    """When OfferCache has the offer, the distributor client is NOT called."""
    from src.bom_enrichment._offer_cache import OfferCache
    from src.bom_enrichment.test_offer_cache import _fake_s3

    # Arrange — pre-populate the cache with a known offer for PN-1.
    cache = OfferCache(bucket="b", prefix="p", s3=_fake_s3())
    cache.put(_offer("graybar", "PN-1", unit_cost_usd=99.99))

    # Client that would explode if called — proves we never call it on cache hit.
    class _ExplodingClient(DistributorClient):
        @property
        def distributor_id(self) -> DistributorId:
            return "graybar"

        def fetch_offer(self, mpn: str) -> DistributorOffer:
            raise AssertionError(f"client called for cached mpn {mpn!r}")

        def close(self) -> None:
            pass

    service = EnrichmentService([_ExplodingClient()], cache=cache)

    # Act
    actual = service.enrich(["PN-1"])

    # Assert — cached offer surfaces, client.fetch_offer never ran
    assert actual["PN-1"].offers[0].unit_cost_usd == 99.99


def test_successful_scrape_is_written_to_cache_but_error_is_not() -> None:
    """Cache miss → scrape → write back. Error offer → no write."""
    from src.bom_enrichment._offer_cache import OfferCache
    from src.bom_enrichment.test_offer_cache import _fake_s3

    # Arrange
    cache = OfferCache(bucket="b", prefix="p", s3=_fake_s3())
    client = _MockClient(
        "graybar",
        {"PN-OK": _offer("graybar", "PN-OK", unit_cost_usd=15.0)},
        # PN-FAIL is missing → _MockClient returns an error offer
    )
    service = EnrichmentService([client], cache=cache)

    # Act
    service.enrich(["PN-OK", "PN-FAIL"])

    # Assert — only the successful offer landed in the cache.
    assert cache.get(distributor="graybar", mpn="PN-OK") is not None
    assert cache.get(distributor="graybar", mpn="PN-FAIL") is None


def test_close_calls_each_client_once() -> None:
    """Service.close() releases every client's resources."""
    # Arrange
    c1 = _MockClient("mouser", {})
    c2 = _MockClient("graybar", {})
    service = EnrichmentService([c1, c2])

    # Act
    service.close()

    # Assert
    assert c1.close_calls == 1
    assert c2.close_calls == 1
