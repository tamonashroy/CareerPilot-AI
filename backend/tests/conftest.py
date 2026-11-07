"""Shared fixtures. Database tests use a real, separate PostgreSQL database.

If PostgreSQL can't be reached, database tests are skipped locally. With REQUIRE_DB_TESTS=1, as in
CI, they fail instead, so a missing database can't produce a false green.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://careerpilot:careerpilot@localhost:5432/careerpilot_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["APP_ENV"] = "test"

from app.db.session import SessionFactory  # noqa: E402
from app.main import create_app  # noqa: E402

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def alembic_config() -> Config:
    return Config(str(BACKEND_ROOT / "alembic.ini"))


async def run_alembic(action: str, revision: str) -> None:
    # In a thread because env.py calls asyncio.run, which can't nest inside a running loop.
    await asyncio.to_thread(getattr(command, action), alembic_config(), revision)


async def _ensure_database_exists() -> None:
    url = make_url(TEST_DATABASE_URL)
    admin = create_async_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
            )
            if not exists:
                await connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        await admin.dispose()


@pytest.fixture(scope="session")
async def db_engine() -> AsyncIterator[AsyncEngine]:
    try:
        await asyncio.wait_for(_ensure_database_exists(), 10)
    except (OSError, TimeoutError) as exc:
        if os.environ.get("REQUIRE_DB_TESTS") == "1":
            pytest.fail(f"PostgreSQL is required but unreachable: {type(exc).__name__}")
        pytest.skip("PostgreSQL is not reachable; start it with: docker compose up -d db")

    await run_alembic("upgrade", "head")
    engine = create_async_engine(TEST_DATABASE_URL)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(db_engine: AsyncEngine) -> SessionFactory:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory.begin() as session:
        await session.execute(text("TRUNCATE background_jobs"))
    return factory


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
