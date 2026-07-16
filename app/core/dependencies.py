from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.external.postgres.engine import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session with automatic commit/rollback."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── AI / MCP singletons ───────────────────────────────────────────────────────
# Populated at application startup (main.py lifespan) and returned by these
# dependency functions. Using module-level references avoids app.state coupling.

_anthropic_client = None
_mcp_server = None


def set_anthropic_client(client) -> None:
    global _anthropic_client
    _anthropic_client = client


def get_anthropic_client():
    return _anthropic_client


def set_mcp_server(server) -> None:
    global _mcp_server
    _mcp_server = server


def get_mcp_server():
    return _mcp_server
