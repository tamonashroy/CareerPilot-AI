import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionFactory
from app.queue import service
from app.queue.handlers import HANDLERS, SAMPLE_JOB_TYPE, JobHandler, PermanentJobError
from app.queue.models import BackgroundJob, JobStatus
from app.queue.worker import Worker

pytestmark = pytest.mark.db


async def _enqueue(session_factory: SessionFactory, **overrides: Any) -> uuid.UUID:
    arguments: dict[str, Any] = {
        "job_type": "test.job",
        "payload": {"n": 1},
        "idempotency_key": f"test:{uuid.uuid4()}",
        **overrides,
    }
    async with session_factory.begin() as session:
        return (await service.enqueue(session, **arguments)).job_id


async def _job(session_factory: SessionFactory, job_id: uuid.UUID) -> BackgroundJob:
    async with session_factory() as session:
        job = await service.get_job(session, job_id)
    assert job is not None
    return job


async def _expire_lease(session_factory: SessionFactory, job_id: uuid.UUID) -> None:
    async with session_factory.begin() as session:
        await session.execute(
            update(BackgroundJob)
            .where(BackgroundJob.id == job_id)
            .values(locked_until=datetime.now(UTC) - timedelta(seconds=1))
        )


async def _make_due(session_factory: SessionFactory, job_id: uuid.UUID) -> None:
    async with session_factory.begin() as session:
        await session.execute(
            update(BackgroundJob)
            .where(BackgroundJob.id == job_id)
            .values(run_at=datetime.now(UTC) - timedelta(seconds=1))
        )


def _worker(session_factory: SessionFactory, handler: JobHandler) -> Worker:
    return Worker(session_factory, {"test.job": handler}, worker_id="test-worker")


async def _succeed(_: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True}


async def _raise(_: dict[str, Any]) -> None:
    raise ValueError("temporary problem")


async def test_duplicate_idempotency_key_returns_the_same_job(
    session_factory: SessionFactory,
) -> None:
    arguments: dict[str, Any] = {"job_type": "test.job", "payload": {}, "idempotency_key": "k1"}
    async with session_factory.begin() as session:
        first = await service.enqueue(session, **arguments)
        second = await service.enqueue(session, **arguments)

    assert first.created is True
    assert second.created is False
    assert first.job_id == second.job_id
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(BackgroundJob)) == 1


async def test_enqueue_rolls_back_with_the_callers_transaction(
    session_factory: SessionFactory,
) -> None:
    with pytest.raises(RuntimeError, match="caller failed"):
        async with session_factory.begin() as session:
            await service.enqueue(session, job_type="t", payload={}, idempotency_key="k2")
            raise RuntimeError("caller failed")

    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(BackgroundJob)) == 0


async def test_invalid_status_is_rejected_by_the_database(session_factory: SessionFactory) -> None:
    job_id = await _enqueue(session_factory)
    with pytest.raises(IntegrityError):
        async with session_factory.begin() as session:
            await session.execute(
                update(BackgroundJob).where(BackgroundJob.id == job_id).values(status="invented")
            )


async def test_concurrent_workers_cannot_claim_the_same_job(
    session_factory: SessionFactory,
) -> None:
    await _enqueue(session_factory)
    claims = await asyncio.gather(
        *(service.claim_next(session_factory, f"worker-{i}", 30) for i in range(8))
    )
    assert len([c for c in claims if c is not None]) == 1


async def test_concurrent_workers_each_get_a_different_job(
    session_factory: SessionFactory,
) -> None:
    job_ids = {await _enqueue(session_factory) for _ in range(5)}
    claims = await asyncio.gather(
        *(service.claim_next(session_factory, f"worker-{i}", 30) for i in range(5))
    )
    claimed_ids = {c.id for c in claims if c is not None}
    # SKIP LOCKED can make a worker miss a job in a race, but never share one.
    assert claimed_ids <= job_ids
    assert len(claimed_ids) == len([c for c in claims if c is not None])
    assert claimed_ids


async def test_future_job_is_not_claimed_until_due(session_factory: SessionFactory) -> None:
    job_id = await _enqueue(session_factory, run_at=datetime.now(UTC) + timedelta(hours=1))
    assert await service.claim_next(session_factory, "w", 30) is None

    await _make_due(session_factory, job_id)
    claim = await service.claim_next(session_factory, "w", 30)
    assert claim is not None
    assert claim.id == job_id


async def test_lease_covers_timeout_plus_grace(session_factory: SessionFactory) -> None:
    job_id = await _enqueue(session_factory, timeout_seconds=100)
    before = datetime.now(UTC)
    assert await service.claim_next(session_factory, "w", 20) is not None

    job = await _job(session_factory, job_id)
    assert job.status == JobStatus.RUNNING
    assert job.attempts == 1
    assert job.locked_by == "w"
    assert job.locked_until is not None
    assert job.locked_until - before >= timedelta(seconds=119)


async def test_success_stores_the_result(session_factory: SessionFactory) -> None:
    job_id = await _enqueue(session_factory)
    assert await _worker(session_factory, _succeed).run_once() is True

    job = await _job(session_factory, job_id)
    assert job.status == JobStatus.SUCCEEDED
    assert job.result == {"ok": True}
    assert job.locked_by is None
    assert job.locked_until is None


async def test_run_once_returns_false_when_queue_is_empty(session_factory: SessionFactory) -> None:
    assert await _worker(session_factory, _succeed).run_once() is False


async def test_error_retries_later_with_backoff(session_factory: SessionFactory) -> None:
    job_id = await _enqueue(session_factory)
    before = datetime.now(UTC)
    await _worker(session_factory, _raise).run_once()

    job = await _job(session_factory, job_id)
    assert job.status == JobStatus.QUEUED
    assert job.attempts == 1
    assert job.last_error == "ValueError: temporary problem"
    assert job.run_at > before
    assert await service.claim_next(session_factory, "w", 30) is None


async def test_job_goes_dead_after_max_attempts(session_factory: SessionFactory) -> None:
    job_id = await _enqueue(session_factory, max_attempts=2)
    worker = _worker(session_factory, _raise)

    await worker.run_once()
    assert (await _job(session_factory, job_id)).status == JobStatus.QUEUED

    await _make_due(session_factory, job_id)
    await worker.run_once()
    job = await _job(session_factory, job_id)
    assert job.status == JobStatus.DEAD
    assert job.attempts == 2

    await _make_due(session_factory, job_id)
    assert await worker.run_once() is False


async def test_permanent_error_fails_without_retry(session_factory: SessionFactory) -> None:
    async def handler(_: dict[str, Any]) -> None:
        raise PermanentJobError("bad input")

    job_id = await _enqueue(session_factory, max_attempts=5)
    await _worker(session_factory, handler).run_once()

    job = await _job(session_factory, job_id)
    assert job.status == JobStatus.FAILED
    assert job.attempts == 1
    assert "bad input" in (job.last_error or "")


async def test_unknown_job_type_fails_permanently(session_factory: SessionFactory) -> None:
    job_id = await _enqueue(session_factory, job_type="no.such.handler")
    await _worker(session_factory, _succeed).run_once()

    job = await _job(session_factory, job_id)
    assert job.status == JobStatus.FAILED
    assert "no.such.handler" in (job.last_error or "")


async def test_timeout_counts_as_a_retryable_failure(session_factory: SessionFactory) -> None:
    async def too_slow(_: dict[str, Any]) -> None:
        await asyncio.sleep(30)

    job_id = await _enqueue(session_factory, timeout_seconds=1)
    await _worker(session_factory, too_slow).run_once()

    job = await _job(session_factory, job_id)
    assert job.status == JobStatus.QUEUED
    assert job.last_error == "timed out after 1s"


async def test_crashed_job_is_reclaimed_and_completes_once(
    session_factory: SessionFactory,
) -> None:
    job_id = await _enqueue(session_factory)
    assert await service.claim_next(session_factory, "crashed-worker", 30) is not None
    assert await service.reclaim_expired(session_factory) == 0

    await _expire_lease(session_factory, job_id)
    assert await service.reclaim_expired(session_factory) == 1

    job = await _job(session_factory, job_id)
    assert job.status == JobStatus.QUEUED
    assert job.last_error == "lease expired"

    calls = 0

    async def counting(_: dict[str, Any]) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"ok": True}

    worker = _worker(session_factory, counting)
    assert await worker.run_once() is True
    assert await worker.run_once() is False
    assert calls == 1

    job = await _job(session_factory, job_id)
    assert job.status == JobStatus.SUCCEEDED
    assert job.attempts == 2


async def test_reclaim_buries_a_job_with_no_attempts_left(session_factory: SessionFactory) -> None:
    job_id = await _enqueue(session_factory, max_attempts=1)
    assert await service.claim_next(session_factory, "crashed-worker", 30) is not None
    await _expire_lease(session_factory, job_id)

    assert await service.reclaim_expired(session_factory) == 1
    assert (await _job(session_factory, job_id)).status == JobStatus.DEAD


async def test_stale_worker_cannot_overwrite_a_newer_attempt(
    session_factory: SessionFactory,
) -> None:
    job_id = await _enqueue(session_factory)
    stale = await service.claim_next(session_factory, "same-worker", 30)
    assert stale is not None
    await _expire_lease(session_factory, job_id)
    await service.reclaim_expired(session_factory)
    current = await service.claim_next(session_factory, "same-worker", 30)
    assert current is not None

    # Same worker ID, so only the attempt number tells the two apart.
    assert await service.complete(session_factory, stale, {"from": "stale"}) is False
    assert await service.retry_or_bury(session_factory, stale, "stale error") is False
    assert await service.fail_permanently(session_factory, stale, "stale error") is False
    assert (await _job(session_factory, job_id)).status == JobStatus.RUNNING

    assert await service.complete(session_factory, current, {"from": "current"}) is True
    job = await _job(session_factory, job_id)
    assert job.status == JobStatus.SUCCEEDED
    assert job.result == {"from": "current"}


async def test_worker_loop_runs_sample_job_and_stops_cleanly(
    session_factory: SessionFactory,
) -> None:
    job_id = await _enqueue(session_factory, job_type=SAMPLE_JOB_TYPE, payload={"message": "hello"})
    worker = Worker(session_factory, HANDLERS, poll_interval_seconds=0.01)
    task = asyncio.create_task(worker.run())

    async with asyncio.timeout(10):
        while (await _job(session_factory, job_id)).status != JobStatus.SUCCEEDED:
            await asyncio.sleep(0.02)
        worker.stop_event.set()
        await task

    assert (await _job(session_factory, job_id)).result == {"echo": "hello"}


async def test_running_job_finishes_when_stop_is_requested(session_factory: SessionFactory) -> None:
    started = asyncio.Event()

    async def slow(_: dict[str, Any]) -> dict[str, Any]:
        started.set()
        await asyncio.sleep(0.2)
        return {"finished": True}

    job_id = await _enqueue(session_factory)
    worker = Worker(session_factory, {"test.job": slow}, poll_interval_seconds=0.01)
    task = asyncio.create_task(worker.run())

    async with asyncio.timeout(10):
        await started.wait()
        worker.stop_event.set()
        await task

    assert (await _job(session_factory, job_id)).status == JobStatus.SUCCEEDED
