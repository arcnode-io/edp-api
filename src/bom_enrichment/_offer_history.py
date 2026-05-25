"""S3-backed offer history — one dated snapshot per (distributor, MPN) per scrape.

OfferCache is the "freshest valid offer" lookup; OfferHistory is the
audit trail. Every successful cache-miss scrape lands a snapshot here
keyed by (distributor, MPN, ISO-date), so downstream BOM enrichment
can compute "price up/down vs last week" deltas.

Snapshot key: `{prefix}/{distributor}/{url-encoded-mpn}/{YYYY-MM-DD}.json`
— one snapshot per day per (distributor, MPN); same-day re-scrapes
overwrite. Pruning of old snapshots is left to S3 lifecycle policy.
"""

import logging
import urllib.parse
from datetime import datetime, timedelta
from typing import Final

from botocore.client import BaseClient

from src.bom_enrichment.enrichment_models import DistributorId, DistributorOffer

logger = logging.getLogger(__name__)

# Reason: keep this independent of cache TTL — history is for trend
# analysis, cache is for re-scrape avoidance. They tune separately.
DEFAULT_DELTA_WINDOW_DAYS: Final[int] = 7


class OfferHistory:
    """S3-backed dated offer snapshots — one per (distributor, MPN, day)."""

    def __init__(self, *, bucket: str, prefix: str, s3: BaseClient) -> None:
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._s3 = s3

    def record(self, offer: DistributorOffer) -> None:
        """Write one dated snapshot. Error offers are skipped."""
        if offer.error is None:
            self._s3.put_object(
                Bucket=self._bucket,
                Key=self._key(offer.distributor, offer.mpn, offer.refreshed_at),
                Body=offer.model_dump_json().encode("utf-8"),
            )

    def list_snapshots(
        self, *, distributor: DistributorId, mpn: str
    ) -> list[DistributorOffer]:
        """Fetch all snapshots for (distributor, MPN), sorted ascending by refreshed_at."""
        prefix = self._dir_prefix(distributor, mpn)
        try:
            resp = self._s3.list_objects_v2(Bucket=self._bucket, Prefix=prefix)
        except Exception:
            logger.exception("offer history list failed for %s", prefix)
            return []
        offers: list[DistributorOffer] = []
        for entry in resp.get("Contents", []):
            try:
                body = self._s3.get_object(Bucket=self._bucket, Key=entry["Key"])[
                    "Body"
                ].read()
                offers.append(DistributorOffer.model_validate_json(body))
            except Exception:
                logger.exception("offer history get failed for %s", entry["Key"])
        offers.sort(key=lambda o: o.refreshed_at)
        return offers

    def _key(self, distributor: str, mpn: str, when: datetime) -> str:
        return f"{self._dir_prefix(distributor, mpn)}{when.date().isoformat()}.json"

    def _dir_prefix(self, distributor: str, mpn: str) -> str:
        safe_mpn = urllib.parse.quote(mpn, safe="")
        return f"{self._prefix}/{distributor}/{safe_mpn}/"


def compute_delta_pct(
    *,
    current: DistributorOffer,
    snapshots: list[DistributorOffer],
    now: datetime,
    days_window: int = DEFAULT_DELTA_WINDOW_DAYS,
) -> float | None:
    """Percent change between current price and the nearest snapshot >= days_window old.

    Returns None when no snapshot is old enough, or when prices are missing.
    Positive = price went up; negative = price went down.
    """
    if current.unit_cost_usd is None:
        return None
    cutoff = now - timedelta(days=days_window)
    older = [
        s for s in snapshots if s.refreshed_at <= cutoff and s.unit_cost_usd is not None
    ]
    if not older:
        return None
    # Nearest one that's still old enough (latest <= cutoff).
    baseline = max(older, key=lambda s: s.refreshed_at)
    # mypy/ty: unit_cost_usd is non-None by filter above.
    assert baseline.unit_cost_usd is not None
    return (
        (current.unit_cost_usd - baseline.unit_cost_usd)
        / baseline.unit_cost_usd
        * 100.0
    )
