"""Operator commands. Sample jobs are enqueued here because there's no authenticated API yet."""

import argparse
import asyncio
import json
import sys
import uuid

from app.db.session import get_engine, get_session_factory
from app.queue import service
from app.queue.handlers import SAMPLE_JOB_TYPE


async def _enqueue_sample(message: str, idempotency_key: str | None) -> int:
    async with get_session_factory().begin() as session:
        queued = await service.enqueue(
            session,
            job_type=SAMPLE_JOB_TYPE,
            payload={"message": message},
            idempotency_key=idempotency_key or f"sample:{uuid.uuid4()}",
        )
    print(json.dumps({"job_id": str(queued.job_id), "created": queued.created}))
    return 0


async def _job_status(job_id: uuid.UUID) -> int:
    async with get_session_factory()() as session:
        job = await service.get_job(session, job_id)
    if job is None:
        print(json.dumps({"error": "job not found"}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "job_id": str(job.id),
                "type": job.type,
                "status": job.status,
                "attempts": job.attempts,
                "result": job.result,
                "last_error": job.last_error,
            }
        )
    )
    return 0


async def _run(args: argparse.Namespace) -> int:
    try:
        if args.command == "enqueue-sample":
            return await _enqueue_sample(args.message, args.idempotency_key)
        return await _job_status(args.job_id)
    finally:
        await get_engine().dispose()


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    sample = commands.add_parser("enqueue-sample", help="Add a sample job to the queue")
    sample.add_argument("--message", default="hello from the sample job")
    sample.add_argument("--idempotency-key", default=None)
    status = commands.add_parser("job-status", help="Show a job's status")
    status.add_argument("job_id", type=uuid.UUID)
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
