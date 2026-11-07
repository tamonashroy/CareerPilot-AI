from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

SessionFactory = async_sessionmaker[AsyncSession]


@lru_cache
def get_engine() -> AsyncEngine:
    url = get_settings().database_url.get_secret_value()
    return create_async_engine(url, pool_pre_ping=True)


@lru_cache
def get_session_factory() -> SessionFactory:
    return async_sessionmaker(get_engine(), expire_on_commit=False)
