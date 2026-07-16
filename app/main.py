"""
FastAPI application entry point.

Wires together all external services and feature pipelines via the lifespan
context manager. Each external service init is guarded with try/except so the
application boots cleanly even when running with stub implementations.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI

from app.core.config import settings
from app.core.logging import setup_logging
from app.api.router import api_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup → yield → shutdown."""
    setup_logging(settings.LOG_LEVEL)
    app.state.settings = settings
    logger.info("Starting Instant Strike Execution Engine [env=%s]", settings.ENVIRONMENT)

    # ── 1. Redis ──────────────────────────────────────────────────────────────
    redis_client = None
    price_window = None
    try:
        from app.external.redis.client import init_redis, close_redis
        from app.external.redis.window import PriceWindow
        redis_client = await init_redis(settings.REDIS_URL)
        price_window = PriceWindow(redis_client)
        app.state.price_window = price_window
        logger.info("Redis initialised")
    except Exception as exc:
        logger.warning("Redis init failed — running without Redis: %s", exc)
        app.state.price_window = None

    # ── 2. Postgres engine ────────────────────────────────────────────────────
    try:
        from app.external.postgres.engine import init_engine
        await init_engine(settings.DATABASE_URL)
        logger.info("Postgres engine initialised")
    except Exception as exc:
        logger.warning("Postgres init failed — DB features will be unavailable: %s", exc)

    # ── 3. Ingestion pipeline ─────────────────────────────────────────────────
    try:
        from app.features.spike_detection.detector import SpikeDetector
        from app.features.ingestion.pipeline import init_pipeline
        from app.features.trading.service import handle_signal
        from app.external.postgres.engine import AsyncSessionLocal

        spike_detector = SpikeDetector(price_window)
        init_pipeline(price_window, spike_detector, handle_signal, AsyncSessionLocal)
        logger.info("Ingestion pipeline wired")
    except Exception as exc:
        logger.warning("Ingestion pipeline wire-up failed (stub): %s", exc)

    # ── 4. DhanHQ consumer ────────────────────────────────────────────────────
    consumer_task = None
    if settings.DHAN_CLIENT_ID and settings.DHAN_ACCESS_TOKEN:
        try:
            from app.external.dhanhq.consumer import DhanFeedConsumer
            from app.features.ingestion.pipeline import ingest_tick

            consumer = DhanFeedConsumer(
                client_id=settings.DHAN_CLIENT_ID,
                access_token=settings.DHAN_ACCESS_TOKEN,
                on_tick=ingest_tick,
            )
            app.state.consumer = consumer
            consumer_task = asyncio.create_task(consumer.start())
            logger.info("DhanHQ consumer started")
        except Exception as exc:
            logger.warning("DhanHQ consumer failed to start (stub): %s", exc)
    else:
        logger.warning(
            "DHAN_CLIENT_ID / DHAN_ACCESS_TOKEN not set — WebSocket consumer disabled"
        )

    # ── 5. AI / MCP layer ────────────────────────────────────────────────────
    anthropic_client = None
    if settings.ANTHROPIC_API_KEY:
        try:
            from app.external.anthropic.client import AnthropicClient
            from app.features.ai.mcp_server import MCPServer
            from app.core.dependencies import set_anthropic_client, set_mcp_server

            anthropic_client = AnthropicClient(
                api_key=settings.ANTHROPIC_API_KEY,
                model=settings.ANTHROPIC_MODEL,
            )
            await anthropic_client.initialise()
            set_anthropic_client(anthropic_client)
            set_mcp_server(MCPServer())
            logger.info("Anthropic client initialised | model=%s", settings.ANTHROPIC_MODEL)
        except Exception as exc:
            logger.warning("Anthropic client init failed — /ask endpoint unavailable: %s", exc)
    else:
        logger.warning("ANTHROPIC_API_KEY not set — AI query endpoint disabled")

    # ── Application is running ────────────────────────────────────────────────
    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("Shutting down…")

    if consumer_task is not None:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass

    try:
        from app.external.redis.client import close_redis
        await close_redis()
    except Exception as exc:
        logger.warning("Redis close error: %s", exc)

    try:
        from app.external.postgres.engine import close_engine
        await close_engine()
    except Exception as exc:
        logger.warning("Postgres close error: %s", exc)

    if anthropic_client is not None:
        try:
            await anthropic_client.close()
        except Exception as exc:
            logger.warning("Anthropic client close error: %s", exc)

    logger.info("Shutdown complete")


app = FastAPI(
    title="Instant Strike Execution Engine",
    description="Low-latency NIFTY options execution engine",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(api_router)
