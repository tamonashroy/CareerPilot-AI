import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.core.config import Settings
from app.core.errors import AppError
from app.main import create_app


def _settings(**overrides: object) -> Settings:
    return Settings(database_url=SecretStr("postgresql+asyncpg://u:p@h/d"), **overrides)  # type: ignore[arg-type]


def _test_app(settings: Settings | None = None) -> FastAPI:
    app = create_app(settings or _settings())

    async def boom() -> None:
        raise RuntimeError("secret detail that must not reach the client")

    async def conflict() -> None:
        raise AppError(409, "already_exists", "It already exists.", {"field": "name"})

    async def item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    app.add_api_route("/boom", boom)
    app.add_api_route("/conflict", conflict)
    app.add_api_route("/items/{item_id}", item)
    return app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=_test_app())
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


async def test_generates_a_correlation_id(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert uuid.UUID(response.headers["X-Request-ID"])


async def test_echoes_a_valid_correlation_id(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"


async def test_replaces_an_unsafe_correlation_id(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-ID": 'bad id"} injected'})
    assert uuid.UUID(response.headers["X-Request-ID"])


async def test_404_uses_the_error_format(client: AsyncClient) -> None:
    response = await client.get("/no-such-page")
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Not Found", "details": None}
    }


async def test_app_error_uses_the_error_format(client: AsyncClient) -> None:
    response = await client.get("/conflict")
    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "already_exists",
            "message": "It already exists.",
            "details": {"field": "name"},
        }
    }


async def test_422_uses_the_error_format_and_omits_the_input(client: AsyncClient) -> None:
    response = await client.get("/items/private-value")
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["field"] == "path.item_id"
    assert "private-value" not in response.text


async def test_500_is_clean_and_keeps_id_and_headers(client: AsyncClient) -> None:
    response = await client.get("/boom")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret detail" not in response.text
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"


async def test_secure_headers(client: AsyncClient) -> None:
    headers = (await client.get("/health")).headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert "default-src 'none'" in headers["Content-Security-Policy"]
    assert "Strict-Transport-Security" not in headers


async def test_hsts_only_in_production() -> None:
    app = _test_app(_settings(app_env="production"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        headers = (await client.get("/health")).headers
    assert "max-age" in headers["Strict-Transport-Security"]


async def test_docs_page_is_served_and_can_load_its_assets(client: AsyncClient) -> None:
    response = await client.get("/docs")
    assert response.status_code == 200
    assert "Content-Security-Policy" not in response.headers


async def test_cors_rejects_unknown_origin_and_allows_listed_one() -> None:
    app = _test_app(_settings(cors_allowed_origins="https://app.example.com"))
    preflight = {"Access-Control-Request-Method": "POST"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        rejected = await client.options(
            "/health", headers={"Origin": "https://evil.example.com", **preflight}
        )
        allowed = await client.options(
            "/health", headers={"Origin": "https://app.example.com", **preflight}
        )
    assert rejected.status_code == 400
    assert "Access-Control-Allow-Origin" not in rejected.headers
    assert allowed.status_code == 200
    assert allowed.headers["Access-Control-Allow-Origin"] == "https://app.example.com"
