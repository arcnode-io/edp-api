"""In-memory job store. Single replica; restarts lose in-flight jobs (per design)."""

from uuid import UUID

from src.jobs.job_record import JobRecord


class JobStore:
    """Dict-backed JobRecord store. Not thread-safe — FastAPI BG tasks share the loop."""

    def __init__(self) -> None:
        self._records: dict[UUID, JobRecord] = {}

    def put(self, record: JobRecord) -> None:
        """Insert or overwrite the record."""
        self._records[record.job_id] = record

    def get(self, job_id: UUID) -> JobRecord | None:
        """Return record if present, else None."""
        return self._records.get(job_id)
