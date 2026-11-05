import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.health import get_expected_revision
from app.db.session import SessionFactory, get_session_factory
from app.main import create_app


def _client_with(session_factory: SessionFactory, revision: str | None = None) -> AsyncClient:
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    if revision is not None:
        app.dependency_overrides[get_expected_revision] = lambda: revision
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_health_ok_without_database(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.db
async def test_ready_ok(session_factory: SessionFactory) -> None:
    async with _client_with(session_factory) as client:
        response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok", "migrations": "ok"}


async def test_ready_503_when_database_is_down() -> None:
    engine = create_async_engine("postgresql+asyncpg://nobody:nothing@127.0.0.1:1/none")
    async with _client_with(async_sessionmaker(engine)) as client:
        response = await client.get("/ready")
    await engine.dispose()

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "not_ready"
    assert error["details"] == {"database": "unavailable", "migrations": "unknown"}
    assert "nothing" not in response.text


@pytest.mark.db
async def test_ready_503_when_migrations_are_behind(session_factory: SessionFactory) -> None:
    async with _client_with(session_factory, revision="a-newer-revision") as client:
        response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json()["error"]["details"] == {"database": "ok", "migrations": "behind"}


async def test_expected_revision_is_the_latest_migration() -> None:
    assert get_expected_revision() == "0002"
