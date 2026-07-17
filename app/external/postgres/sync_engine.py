"""Singleton synchronous SQLAlchemy engine for Celery task context.

Celery workers run in a synchronous context and cannot use the async engine.
This module creates ONE engine per worker process (not per task), which means
the connection pool is shared across all tasks in that process — avoiding the
connection pool exhaustion that occurs when create_engine() is called per task.

Usage:
    from app.external.postgres.sync_engine import get_sync_session

    with get_sync_session() as session:
        result = session.execute(...)
"""
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

_engine = None
_SessionLocal: sessionmaker | None = None


def _get_engine():
    """Return (or lazily create) the process-level sync engine."""
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(
            settings.sync_database_url,
            pool_size=20,    # one per Celery worker thread; safe up to 10x workers
            max_overflow=30,
            pool_pre_ping=True,
        )
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
        logger.info("Sync Postgres engine initialised (pid-level singleton)")
    return _engine


def get_sync_session() -> Session:
    """Return a new synchronous Session bound to the singleton engine."""
    _get_engine()
    return _SessionLocal()
