"""Async SQLAlchemy engine/session management."""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_maker: async_sessionmaker[AsyncSession] | None = None


def init_engine(url: str | None = None) -> async_sessionmaker[AsyncSession]:
    global _engine, _maker
    _engine = create_async_engine(url or get_settings().database_url, pool_pre_ping=True)
    _maker = async_sessionmaker(_engine, expire_on_commit=False)
    return _maker


def session_maker() -> async_sessionmaker[AsyncSession]:
    return _maker or init_engine()


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_maker()() as session:
        yield session


async def dispose_engine() -> None:
    if _engine is not None:
        await _engine.dispose()
