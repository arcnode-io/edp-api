"""JobStore unit tests."""

from uuid import UUID

from src.jobs.job_record import JobRecord
from src.jobs.job_store import JobStore
from src.shared.schemas.artifact import JobStatus

JOB_ID: UUID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def test_get_returns_none_for_missing_job() -> None:
    """Lookup of unknown job returns None."""
    # Arrange
    store = JobStore()

    # Act
    actual = store.get(JOB_ID)

    # Assert
    assert actual is None


def test_put_then_get_roundtrips() -> None:
    """Stored record retrieved verbatim."""
    # Arrange
    store = JobStore()
    record = JobRecord(job_id=JOB_ID, status=JobStatus.RUNNING, edp_artifact_urls=[])

    # Act
    store.put(record)
    actual = store.get(JOB_ID)

    # Assert
    assert actual == record


def test_put_overwrites_existing() -> None:
    """Same job_id put twice -> last wins."""
    # Arrange
    store = JobStore()
    initial = JobRecord(job_id=JOB_ID, status=JobStatus.RUNNING, edp_artifact_urls=[])
    updated = JobRecord(job_id=JOB_ID, status=JobStatus.COMPLETE, edp_artifact_urls=[])

    # Act
    store.put(initial)
    store.put(updated)
    actual = store.get(JOB_ID)

    # Assert
    assert actual is not None
    assert actual.status == JobStatus.COMPLETE
