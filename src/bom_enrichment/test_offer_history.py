"""OfferHistory unit tests — S3-keyed dated snapshots + delta computation."""

from datetime import UTC, datetime

from src.bom_enrichment._offer_history import OfferHistory, compute_delta_pct
from src.bom_enrichment.enrichment_models import DistributorOffer
from src.bom_enrichment.test_offer_cache import _fake_s3


def _offer(refreshed_at: datetime, price: float) -> DistributorOffer:
    return DistributorOffer(
        distributor="graybar",
        mpn="PN-1",
        unit_cost_usd=price,
        refreshed_at=refreshed_at,
    )


def test_record_writes_per_day_snapshot_and_list_returns_them_sorted() -> None:
    # Arrange
    s3 = _fake_s3()
    history = OfferHistory(bucket="b", prefix="hist", s3=s3)
    d1 = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)
    d2 = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
    history.record(_offer(d1, price=100.0))
    history.record(_offer(d2, price=110.0))

    # Act
    snaps = history.list_snapshots(distributor="graybar", mpn="PN-1")

    # Assert — both present, sorted ascending by refreshed_at
    assert [s.unit_cost_usd for s in snaps] == [100.0, 110.0]


def test_compute_delta_pct_against_snapshot_within_window() -> None:
    # Arrange — 7-day-old snapshot at $100, current at $110 → +10%
    old = _offer(datetime(2026, 5, 17, 12, 0, tzinfo=UTC), price=100.0)
    current = _offer(datetime(2026, 5, 24, 12, 0, tzinfo=UTC), price=110.0)

    # Act
    delta = compute_delta_pct(
        current=current, snapshots=[old], now=current.refreshed_at, days_window=7
    )

    # Assert
    assert delta is not None
    assert round(delta, 2) == 10.0


def test_compute_delta_pct_returns_none_when_no_old_snapshot() -> None:
    # Arrange — only today's snapshot exists; no prior history to compare
    current = _offer(datetime(2026, 5, 24, 12, 0, tzinfo=UTC), price=110.0)

    # Act
    delta = compute_delta_pct(
        current=current, snapshots=[current], now=current.refreshed_at, days_window=7
    )

    # Assert
    assert delta is None
