import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import run_alembic

pytestmark = pytest.mark.db


async def _table_names(engine: AsyncEngine) -> list[str]:
    async with engine.connect() as connection:
        return await connection.run_sync(lambda c: inspect(c).get_table_names())


async def test_upgrade_downgrade_upgrade(db_engine: AsyncEngine) -> None:
    assert "background_jobs" in await _table_names(db_engine)

    await run_alembic("downgrade", "0001")
    assert "background_jobs" not in await _table_names(db_engine)

    await run_alembic("downgrade", "base")
    await run_alembic("upgrade", "head")
    assert "background_jobs" in await _table_names(db_engine)


async def test_pgvector_is_available(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as connection:
        found = await connection.scalar(
            text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
        )
    assert found == 1


async def test_postgres_major_version_is_16(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as connection:
        version = await connection.scalar(text("SHOW server_version_num"))
    assert str(version).startswith("16")
