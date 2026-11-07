"""Operational probes, kept outside /api/v1 because they aren't part of the versioned API."""

import asyncio
import logging
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from app.core.errors import AppError
from app.db.session import SessionFactory, get_session_factory

logger = logging.getLogger(__name__)
router = APIRouter(tags=["operations"])

BACKEND_ROOT = Path(__file__).resolve().parents[2]
READY_TIMEOUT_SECONDS = 3.0


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadyResponse(BaseModel):
    status: Literal["ready"] = "ready"
    database: Literal["ok"] = "ok"
    migrations: Literal["ok"] = "ok"


@lru_cache
def get_expected_revision() -> str | None:
    config = Config()
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return ScriptDirectory.from_config(config).get_current_head()


async def _current_revision(session_factory: SessionFactory) -> str | None:
    async with session_factory() as session:
        exists = await session.scalar(text("SELECT to_regclass('alembic_version')"))
        if exists is None:
            return None
        result = await session.scalar(text("SELECT version_num FROM alembic_version"))
        return str(result) if result is not None else None


@router.get("/health")
async def health() -> HealthResponse:
    return HealthResponse()


@router.get("/ready", responses={503: {"description": "Not ready"}})
async def ready(
    session_factory: Annotated[SessionFactory, Depends(get_session_factory)],
    expected_revision: Annotated[str | None, Depends(get_expected_revision)],
) -> ReadyResponse:
    try:
        current = await asyncio.wait_for(_current_revision(session_factory), READY_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.warning("readiness_database_failed", extra={"error_type": type(exc).__name__})
        raise AppError(
            503,
            "not_ready",
            "The service is not ready.",
            {"database": "unavailable", "migrations": "unknown"},
        ) from exc

    if current != expected_revision:
        raise AppError(
            503,
            "not_ready",
            "The service is not ready.",
            {"database": "ok", "migrations": "behind"},
        )
    return ReadyResponse()
