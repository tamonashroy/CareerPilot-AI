"""The worker process. Run with: python -m app.queue.worker"""

import asyncio
import contextlib
import logging
import os
import signal
import socket
import time
import uuid
from collections.abc import Mapping

from app.core.config import get_settings
from app.core.logging import configure_logging, correlation_id
from app.db.session import SessionFactory, get_session_factory
from app.queue import service
from app.queue.handlers import HANDLERS, JobHandler, PermanentJobError

logger = logging.getLogger(__name__)


class Worker:
    def __init__(
        self,
        session_factory: SessionFactory,
        handlers: Mapping[str, JobHandler],
        *,
        worker_id: str | None = None,
        poll_interval_seconds: float = 1.0,
        lease_grace_seconds: int = 30,
        reclaim_interval_seconds: float = 30.0,
    ) -> None:
        self.session_factory = session_factory
        self.handlers = handlers
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self.poll_interval_seconds = poll_interval_seconds
        self.lease_grace_seconds = lease_grace_seconds
        self.reclaim_interval_seconds = reclaim_interval_seconds
        self.stop_event = asyncio.Event()

    async def run_once(self) -> bool:
        """Runs one job if one is due. Returns whether a job was claimed."""
        claim = await service.claim_next(
            self.session_factory, self.worker_id, self.lease_grace_seconds
        )
        if claim is None:
            return False

        token = correlation_id.set(f"job-{claim.id}")
        try:
            logger.info(
                "job_started",
                extra={"job_id": str(claim.id), "job_type": claim.type, "attempt": claim.attempts},
            )
            await self._execute(claim)
        finally:
            correlation_id.reset(token)
        return True

    async def _execute(self, claim: service.ClaimedJob) -> None:
        handler = self.handlers.get(claim.type)
        outcome = "succeeded"
        recorded = True
        try:
            if handler is None:
                raise PermanentJobError(f"no handler for job type {claim.type!r}")
            result = await asyncio.wait_for(handler(claim.payload), claim.timeout_seconds)
            recorded = await service.complete(self.session_factory, claim, result)
        except PermanentJobError as exc:
            outcome = "failed"
            recorded = await service.fail_permanently(self.session_factory, claim, _describe(exc))
        except TimeoutError:
            outcome = "retry_or_dead"
            error = f"timed out after {claim.timeout_seconds}s"
            recorded = await service.retry_or_bury(self.session_factory, claim, error)
        except Exception as exc:
            outcome = "retry_or_dead"
            recorded = await service.retry_or_bury(self.session_factory, claim, _describe(exc))

        # The error text stays on the job row and out of the logs: it can contain user data.
        logger.info(
            "job_finished" if recorded else "job_result_discarded_lease_lost",
            extra={"job_id": str(claim.id), "job_type": claim.type, "outcome": outcome},
        )

    async def run(self) -> None:
        logger.info("worker_started", extra={"worker_id": self.worker_id})
        next_reclaim = 0.0
        while not self.stop_event.is_set():
            claimed = False
            try:
                if time.monotonic() >= next_reclaim:
                    reclaimed = await service.reclaim_expired(self.session_factory)
                    if reclaimed:
                        logger.warning("jobs_reclaimed", extra={"count": reclaimed})
                    next_reclaim = time.monotonic() + self.reclaim_interval_seconds
                claimed = await self.run_once()
            except Exception:
                # A database outage shouldn't kill the worker: keep polling until it's back.
                logger.exception("worker_loop_error")
            if not claimed:
                await self._sleep_until_next_poll()
        logger.info("worker_stopped", extra={"worker_id": self.worker_id})

    async def _sleep_until_next_poll(self) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self.stop_event.wait(), self.poll_interval_seconds)


def _describe(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def _install_signal_handlers(worker: Worker) -> None:
    loop = asyncio.get_running_loop()

    def request_stop(*_: object) -> None:
        # Stops between jobs, so a running job gets to finish.
        loop.call_soon_threadsafe(worker.stop_event.set)

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, request_stop)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    worker = Worker(
        get_session_factory(),
        HANDLERS,
        poll_interval_seconds=settings.worker_poll_interval_seconds,
        lease_grace_seconds=settings.worker_lease_grace_seconds,
        reclaim_interval_seconds=settings.worker_reclaim_interval_seconds,
    )
    _install_signal_handlers(worker)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
