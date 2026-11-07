"""The PostgreSQL job queue. All job state changes go through this module."""

import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import DateTime, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.session import SessionFactory
from app.queue.models import BackgroundJob, JobStatus

BACKOFF_BASE_SECONDS = 5.0
BACKOFF_MAX_SECONDS = 600.0
MAX_ERROR_LENGTH = 2000


@dataclass(frozen=True)
class EnqueueResult:
    job_id: uuid.UUID
    created: bool


@dataclass(frozen=True)
class ClaimedJob:
    id: uuid.UUID
    type: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int
    timeout_seconds: int
    worker_id: str


def backoff_seconds(attempt: int) -> float:
    """Exponential backoff with equal jitter: half the delay is fixed, half is random."""
    delay: float = min(BACKOFF_BASE_SECONDS * 2.0 ** (attempt - 1), BACKOFF_MAX_SECONDS)
    return delay / 2 + random.uniform(0, delay / 2)  # noqa: S311  # not security-sensitive


async def enqueue(
    session: AsyncSession,
    *,
    job_type: str,
    payload: dict[str, Any],
    idempotency_key: str,
    max_attempts: int = 5,
    timeout_seconds: int = 300,
    run_at: datetime | None = None,
) -> EnqueueResult:
    """Adds a job in the caller's transaction, so it commits along with the caller's own changes.

    Enqueuing an existing idempotency key returns the existing job and changes nothing.
    """
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "type": job_type,
        "payload": payload,
        "status": JobStatus.QUEUED.value,
        "idempotency_key": idempotency_key,
        "attempts": 0,
        "max_attempts": max_attempts,
        "timeout_seconds": timeout_seconds,
    }
    if run_at is not None:
        values["run_at"] = run_at

    statement = (
        insert(BackgroundJob)
        .values(**values)
        .on_conflict_do_nothing(index_elements=[BackgroundJob.idempotency_key])
        .returning(BackgroundJob.id)
    )
    created_id = (await session.execute(statement)).scalar_one_or_none()
    if created_id is not None:
        return EnqueueResult(created_id, created=True)

    existing_id = await session.scalar(
        select(BackgroundJob.id).where(BackgroundJob.idempotency_key == idempotency_key)
    )
    if existing_id is None:
        # The conflicting insert belongs to a transaction this one can't see yet, or that rolled
        # back. Either way the caller's retry resolves it.
        raise RuntimeError("idempotency key conflict could not be resolved; retry the enqueue")
    return EnqueueResult(existing_id, created=False)


async def claim_next(
    session_factory: SessionFactory, worker_id: str, lease_grace_seconds: int
) -> ClaimedJob | None:
    """Claims the next due job and commits, so the handler runs outside this transaction."""
    async with session_factory.begin() as session:
        job = await session.scalar(
            select(BackgroundJob)
            .where(BackgroundJob.status == JobStatus.QUEUED, BackgroundJob.run_at <= _now())
            .order_by(BackgroundJob.run_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            return None
        job.status = JobStatus.RUNNING.value
        job.attempts += 1
        job.locked_by = worker_id
        job.locked_until = await _now_plus(
            session, timedelta(seconds=job.timeout_seconds + lease_grace_seconds)
        )
        return ClaimedJob(
            id=job.id,
            type=job.type,
            payload=job.payload,
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            timeout_seconds=job.timeout_seconds,
            worker_id=worker_id,
        )


async def complete(
    session_factory: SessionFactory, claim: ClaimedJob, result: dict[str, Any] | None
) -> bool:
    """Marks the job succeeded. Returns False if this worker no longer holds the job."""
    return await _finish(
        session_factory,
        claim,
        status=JobStatus.SUCCEEDED,
        result=result,
        last_error=None,
    )


async def fail_permanently(session_factory: SessionFactory, claim: ClaimedJob, error: str) -> bool:
    return await _finish(session_factory, claim, status=JobStatus.FAILED, last_error=error)


async def retry_or_bury(session_factory: SessionFactory, claim: ClaimedJob, error: str) -> bool:
    """Schedules another attempt with backoff, or marks the job dead if none remain."""
    if claim.attempts >= claim.max_attempts:
        return await _finish(session_factory, claim, status=JobStatus.DEAD, last_error=error)
    delay = timedelta(seconds=backoff_seconds(claim.attempts))
    return await _finish(
        session_factory, claim, status=JobStatus.QUEUED, last_error=error, run_at=_now() + delay
    )


async def reclaim_expired(session_factory: SessionFactory) -> int:
    """Recovers jobs whose lease ran out, which means their worker crashed or hung."""
    expired = [
        BackgroundJob.status == JobStatus.RUNNING,
        BackgroundJob.locked_until < _now(),
    ]
    released = {"locked_by": None, "locked_until": None, "last_error": "lease expired"}
    async with session_factory.begin() as session:
        buried = await session.execute(
            update(BackgroundJob)
            .where(*expired, BackgroundJob.attempts >= BackgroundJob.max_attempts)
            .values(status=JobStatus.DEAD.value, **released)
            .returning(BackgroundJob.id)
        )
        requeued = await session.execute(
            update(BackgroundJob)
            .where(*expired, BackgroundJob.attempts < BackgroundJob.max_attempts)
            .values(status=JobStatus.QUEUED.value, run_at=_now(), **released)
            .returning(BackgroundJob.id)
        )
        return len(buried.all()) + len(requeued.all())


async def get_job(session: AsyncSession, job_id: uuid.UUID) -> BackgroundJob | None:
    return await session.get(BackgroundJob, job_id)


async def _finish(
    session_factory: SessionFactory,
    claim: ClaimedJob,
    *,
    status: JobStatus,
    last_error: str | None,
    result: dict[str, Any] | None = None,
    run_at: ColumnElement[datetime] | None = None,
) -> bool:
    values: dict[str, Any] = {
        "status": status.value,
        "locked_by": None,
        "locked_until": None,
        "last_error": last_error[:MAX_ERROR_LENGTH] if last_error else None,
        "result": result,
    }
    if run_at is not None:
        values["run_at"] = run_at

    async with session_factory.begin() as session:
        # Fencing: a worker whose job was reclaimed no longer matches, so it can't overwrite the
        # newer attempt.
        finished = await session.execute(
            update(BackgroundJob)
            .where(
                BackgroundJob.id == claim.id,
                BackgroundJob.status == JobStatus.RUNNING,
                BackgroundJob.locked_by == claim.worker_id,
                BackgroundJob.attempts == claim.attempts,
            )
            .values(**values)
            .returning(BackgroundJob.id)
        )
        return finished.scalar_one_or_none() is not None


def _now() -> ColumnElement[datetime]:
    # Database time, so every worker shares one clock. Unlike now(), this advances within a
    # transaction.
    return func.clock_timestamp(type_=DateTime(timezone=True))


async def _now_plus(session: AsyncSession, delta: timedelta) -> datetime:
    return (await session.execute(select(_now() + delta))).scalar_one()
