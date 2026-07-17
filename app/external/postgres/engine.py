import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None

# Will be replaced after init_engine() is called
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    expire_on_commit=False
)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


async def init_engine(database_url: str) -> AsyncEngine:
    """Create and verify the async SQLAlchemy engine."""
    global _engine, AsyncSessionLocal
    _engine = create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )
    AsyncSessionLocal = async_sessionmaker(
        bind=_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    logger.info("Postgres engine initialised")
    return _engine


async def get_engine() -> AsyncEngine:
    """Return the active engine, raising if not initialised."""
    if _engine is None:
        raise RuntimeError("Postgres engine has not been initialised — call init_engine() first")
    return _engine


async def close_engine() -> None:
    """Dispose of the engine connection pool."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        logger.info("Postgres engine closed")
