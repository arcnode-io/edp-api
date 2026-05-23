"""In-memory job store. Single replica; restarts lose in-flight jobs (per design).

Why ephemeral is fine:
    The pipeline is deterministic — every ArtifactRef URL is a pure function
    of the ConfiguratorPayload (see `pipeline.artifact_urls`). Artifact bytes
    are the only persistent state; the job record is a status projection over
    the in-flight write. A lost RUNNING record means platform-api never gets
    a terminal status for that `job_id`; it re-POSTs the same payload, gets
    a new `job_id` back, and the pipeline writes to the same S3 keys (idempotent
    overwrite). No artifact data is lost; no business invariant is violated.

Failure contract with platform-api:
    - 202 returned immediately with `job_id` + status_url.
    - Poll status_url. RUNNING for the pipeline duration, then COMPLETE or FAILED.
    - If status_url returns 404 (process restart between POST and poll), or RUNNING
      doesn't terminate within the timeout, re-POST the original payload. Safe.
    - Two concurrent POSTs of the same payload race on the same S3 keys; last
      writer wins. Pipeline is deterministic so bytes are equivalent.
"""

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
