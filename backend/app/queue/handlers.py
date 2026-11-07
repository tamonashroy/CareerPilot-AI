"""Job handlers. Each one must be idempotent, because a crashed job runs again."""

from collections.abc import Awaitable, Callable
from typing import Any

JobHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]

SAMPLE_JOB_TYPE = "sample.echo"


class PermanentJobError(Exception):
    """Raised by a handler when retrying can't help. The job ends as `failed`."""


async def sample_echo(payload: dict[str, Any]) -> dict[str, Any]:
    return {"echo": payload.get("message")}


HANDLERS: dict[str, JobHandler] = {SAMPLE_JOB_TYPE: sample_echo}
