"""S3-backed TTL cache for per-distributor MPN offers.

Per-distributor portals are slow + rate-limited (Playwright login + per-MPN
search). Re-running the BOM pipeline for the same deployment profile
shouldn't re-hammer the portals. This cache stores offers keyed by
(distributor, MPN) with a 7-day default TTL — pricing/stock drift on
industrial-grade equipment is slow enough that a week-old offer is still
a reasonable starting point for procurement.

Errors are NOT cached. A transient portal outage today shouldn't poison
the cache for a week; next run gets a fresh attempt.
"""

import logging
import urllib.parse
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Final

from botocore.client import BaseClient

from src.bom_enrichment.enrichment_models import DistributorId, DistributorOffer

logger = logging.getLogger(__name__)

_DEFAULT_TTL_DAYS: Final[int] = 7


class OfferCache:
    """S3-backed offer cache. One JSON object per (distributor, MPN)."""

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str,
        s3: BaseClient,
        ttl_days: int = _DEFAULT_TTL_DAYS,
        now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._s3 = s3
        self._ttl = timedelta(days=ttl_days)
        self._now_fn = now_fn

    def get(self, *, distributor: DistributorId, mpn: str) -> DistributorOffer | None:
        """Return cached offer if present + non-expired, else None."""
        key = self._key(distributor, mpn)
        try:
            body = self._s3.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        except Exception as e:
            code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
            if code in {"NoSuchKey", "404", "NotFound"}:
                return None
            logger.warning("offer cache get failed for %s: %r", key, e)
            return None
        offer = DistributorOffer.model_validate_json(body)
        if self._now_fn() - offer.refreshed_at > self._ttl:
            return None
        return offer

    def put(self, offer: DistributorOffer) -> None:
        """Write offer JSON to S3. Error offers are skipped (don't poison cache)."""
        if offer.error is not None:
            return
        key = self._key(offer.distributor, offer.mpn)
        self._s3.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=offer.model_dump_json().encode("utf-8"),
        )

    def _key(self, distributor: str, mpn: str) -> str:
        """`{prefix}/{distributor}/{url-encoded-mpn}.json` — MPNs may contain /."""
        safe_mpn = urllib.parse.quote(mpn, safe="")
        return f"{self._prefix}/{distributor}/{safe_mpn}.json"
