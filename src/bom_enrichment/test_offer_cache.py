"""OfferCache unit tests — S3-backed TTL cache for DistributorOffer.

Uses a fake S3 client (dict-backed) so tests stay fast + offline. Real
S3 round-tripping is exercised by the existing localstack integration
test in tests/.
"""

from datetime import UTC, datetime, timedelta
from typing import cast

from botocore.client import BaseClient

from src.bom_enrichment._offer_cache import OfferCache
from src.bom_enrichment.enrichment_models import DistributorOffer


def _fake_s3() -> BaseClient:
    """_FakeS3 cast to the boto3 BaseClient type ty expects."""
    return cast(BaseClient, _FakeS3())


class _FakeS3Error(Exception):
    """Stand-in for botocore ClientError; OfferCache checks `response['Error']['Code']`."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class _FakeS3:
    """Minimum boto3-S3 surface OfferCache needs: get_object + put_object."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], bytes] = {}

    def get_object(self, *, Bucket: str, Key: str) -> dict:  # noqa: N803
        if (Bucket, Key) not in self._store:
            raise _FakeS3Error("NoSuchKey")
        body = self._store[(Bucket, Key)]
        return {"Body": _BodyStream(body)}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> None:  # noqa: N803
        self._store[(Bucket, Key)] = Body


class _BodyStream:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


def _offer(
    mpn: str, refreshed_at: datetime, unit_cost_usd: float = 10.0
) -> DistributorOffer:
    return DistributorOffer(
        distributor="graybar",
        mpn=mpn,
        unit_cost_usd=unit_cost_usd,
        refreshed_at=refreshed_at,
    )


def test_put_then_get_roundtrips_offer() -> None:
    # Arrange
    now = datetime(2026, 5, 24, 12, 0, tzinfo=UTC)
    cache = OfferCache(bucket="b", prefix="p", s3=_fake_s3(), now_fn=lambda: now)
    offer = _offer("PN-1", refreshed_at=now, unit_cost_usd=42.5)

    # Act
    cache.put(offer)
    actual = cache.get(distributor="graybar", mpn="PN-1")

    # Assert
    assert actual is not None
    assert actual.unit_cost_usd == 42.5
    assert actual.mpn == "PN-1"


def test_get_returns_none_when_entry_expired() -> None:
    # Arrange — write an offer 8 days ago, read with default 7-day TTL.
    # Share one fake-S3 store across the two cache instances by reaching in.
    write_time = datetime(2026, 5, 16, 12, 0, tzinfo=UTC)
    read_time = write_time + timedelta(days=8)
    s3 = _fake_s3()
    cache_write = OfferCache(bucket="b", prefix="p", s3=s3, now_fn=lambda: write_time)
    cache_write.put(_offer("PN-1", refreshed_at=write_time))
    cache_read = OfferCache(bucket="b", prefix="p", s3=s3, now_fn=lambda: read_time)

    # Act
    actual = cache_read.get(distributor="graybar", mpn="PN-1")

    # Assert
    assert actual is None


def test_get_returns_none_on_cache_miss() -> None:
    # Arrange
    cache = OfferCache(bucket="b", prefix="p", s3=_fake_s3())

    # Act
    actual = cache.get(distributor="graybar", mpn="UNKNOWN-PN")

    # Assert
    assert actual is None
