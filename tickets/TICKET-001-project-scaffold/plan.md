# Plan: TICKET-001 — Project Scaffold & DevOps Setup

## Branch
```bash
git checkout -b feature/TICKET-001-project-scaffold
```

## Step 1 — Create Full Directory Tree
```bash
mkdir -p app/core
mkdir -p app/external/{dhanhq,redis,postgres/migrations/versions,celery,anthropic,webhook}
mkdir -p app/features/{ingestion,spike_detection,trading,notifications,ai}
mkdir -p app/api/routes
mkdir -p app/metrics
mkdir -p docker/webhook_mock
mkdir -p scripts tests/fixtures

# __init__.py for every package
find app -type d -exec touch {}/__init__.py \;
```

## Step 2 — `requirements.txt`
```
# Web framework
fastapi==0.115.0
uvicorn[standard]==0.30.0
python-multipart==0.0.12

# Config
pydantic-settings==2.4.0

# Database (async)
sqlalchemy[asyncio]==2.0.36
asyncpg==0.29.0
psycopg2-binary==2.9.9
alembic==1.13.3

# Redis
redis[hiredis]==5.1.0

# Task queue
celery[redis]==5.4.0

# DhanHQ
dhanhq==2.0.2

# AI
anthropic==0.34.0
fastmcp==2.0.0

# Observability
numpy==2.1.0
matplotlib==3.9.0

# HTTP client (notifications)
httpx==0.27.0
```

## Step 3 — `app/core/config.py`
```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # PostgreSQL
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@postgres:5432/engine"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    # DhanHQ
    DHAN_CLIENT_ID: str = ""
    DHAN_ACCESS_TOKEN: str = ""

    # AI
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-haiku-4-5-20251001"

    # Notification
    WEBHOOK_URL: str = "http://webhook-mock:8001/notify"
    WEBHOOK_TIMEOUT_SECONDS: int = 10

    # App
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"

settings = Settings()
```

## Step 4 — `app/core/logging.py`
```python
import logging
import sys

def setup_logging(level: str = "INFO") -> None:
    fmt = (
        '{"time":"%(asctime)s","level":"%(levelname)s",'
        '"logger":"%(name)s","msg":"%(message)s"}'
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt))
    logging.root.handlers = [handler]
    logging.root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # Silence noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
```

## Step 5 — `app/core/exceptions.py`
```python
class ExecutionEngineError(Exception):
    """Base exception for all domain errors."""

class PipelineError(ExecutionEngineError):
    """Raised when tick ingestion pipeline fails unrecoverably."""

class TradeError(ExecutionEngineError):
    """Raised when trade simulation or persistence fails."""
```

## Step 6 — `app/core/dependencies.py`
```python
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from app.external.postgres.engine import AsyncSessionLocal

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

## Step 7 — `app/api/routes/health.py`
```python
from fastapi import APIRouter, Request

router = APIRouter(tags=["system"])

@router.get("/health")
async def health(request: Request):
    """System health check. Includes feed consumer state."""
    consumer = getattr(request.app.state, "consumer", None)
    return {
        "status": "ok",
        "environment": request.app.state.settings.ENVIRONMENT,
        "feed_state": getattr(consumer, "state", "disabled"),
    }
```

## Step 8 — `app/api/router.py`
```python
from fastapi import APIRouter
from app.api.routes.health import router as health_router
from app.api.routes.replay import router as replay_router
from app.api.routes.metrics import router as metrics_router
from app.features.trading.router import router as trading_router
from app.features.ai.router import router as ai_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(replay_router)
api_router.include_router(metrics_router)
api_router.include_router(trading_router, prefix="/trades")
api_router.include_router(ai_router)
```

## Step 9 — `app/main.py`
```python
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.core.logging import setup_logging
from app.api.router import api_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.LOG_LEVEL)
    app.state.settings = settings

    # 1. Init Redis
    from app.external.redis.client import init_redis, close_redis
    from app.external.redis.window import PriceWindow
    redis = await init_redis(settings.REDIS_URL)
    price_window = PriceWindow(redis)
    app.state.price_window = price_window

    # 2. Init Postgres engine (verify connectivity)
    from app.external.postgres.engine import init_engine
    await init_engine(settings.DATABASE_URL)

    # 3. Wire ingestion pipeline
    from app.features.spike_detection.detector import SpikeDetector
    from app.features.ingestion.pipeline import init_pipeline
    from app.features.trading.service import handle_signal
    from app.external.postgres.engine import AsyncSessionLocal

    spike_detector = SpikeDetector(price_window)
    init_pipeline(price_window, spike_detector, handle_signal, AsyncSessionLocal)

    # 4. Start DhanHQ consumer (if credentials present)
    consumer_task = None
    if settings.DHAN_CLIENT_ID and settings.DHAN_ACCESS_TOKEN:
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
    else:
        logger.warning("DhanHQ credentials not set — WebSocket consumer disabled")

    yield  # Application running

    # Shutdown
    if consumer_task:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass
    await close_redis()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Instant Strike Execution Engine",
    description="Low-latency NIFTY options execution engine",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(api_router)
```

## Step 10 — `Dockerfile`
```dockerfile
FROM python:3.12-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

FROM base AS deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM deps AS final
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "warning"]
```

## Step 11 — `docker-compose.yml`
```yaml
version: "3.9"

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: engine
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user -d engine"]
      interval: 5s
      timeout: 3s
      retries: 5

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    command: redis-server --save "" --appendonly no  # in-memory, no persistence
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  app:
    build:
      context: .
      dockerfile: Dockerfile
      target: final
    ports: ["8000:8000"]
    env_file: .env
    depends_on:
      postgres: {condition: service_healthy}
      redis: {condition: service_healthy}
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:8000/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 15s
    restart: unless-stopped

  celery-worker:
    build:
      context: .
      dockerfile: Dockerfile
      target: final
    command: >
      celery -A app.external.celery.app worker
      --loglevel=info
      --concurrency=4
      --queues=notifications,reconciliation,default
    env_file: .env
    depends_on:
      redis: {condition: service_healthy}
      postgres: {condition: service_healthy}
    restart: unless-stopped

  celery-beat:
    build:
      context: .
      dockerfile: Dockerfile
      target: final
    command: >
      celery -A app.external.celery.app beat
      --loglevel=info
      --pidfile=/tmp/celerybeat.pid
    env_file: .env
    depends_on:
      redis: {condition: service_healthy}
    restart: unless-stopped

  webhook-mock:
    build:
      context: ./docker/webhook_mock
      dockerfile: Dockerfile
    ports: ["8001:8001"]
    restart: unless-stopped

volumes:
  pgdata:
```

## Step 12 — `docker/webhook_mock/Dockerfile`
```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install fastapi uvicorn
COPY server.py .
EXPOSE 8001
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
```

## Step 13 — `docker/webhook_mock/server.py`
```python
import logging
from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webhook-mock")
app = FastAPI(title="Webhook Mock")

@app.post("/notify")
async def notify(request: Request):
    body = await request.json()
    logger.info(f"[NOTIFICATION] {body.get('message', body)}")
    return {"status": "delivered"}

@app.get("/health")
async def health():
    return {"status": "ok"}
```

## Step 14 — `.env.example`
```env
# ── PostgreSQL ──────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/engine

# ── Redis ────────────────────────────────────────────────
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# ── DhanHQ Feed ──────────────────────────────────────────
DHAN_CLIENT_ID=your_dhan_client_id_here
DHAN_ACCESS_TOKEN=your_dhan_access_token_here

# ── AI Layer ─────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-haiku-4-5-20251001

# ── Notification ─────────────────────────────────────────
WEBHOOK_URL=http://webhook-mock:8001/notify
WEBHOOK_TIMEOUT_SECONDS=10

# ── Application ──────────────────────────────────────────
LOG_LEVEL=INFO
ENVIRONMENT=development
```

## Verification
```bash
# Build and start
docker compose up --build -d

# Wait for health
sleep 15 && curl http://localhost:8000/health

# Verify Celery can see the app
docker compose exec celery-worker \
  celery -A app.external.celery.app inspect ping

# No circular import errors
docker compose exec app python -c "from app.main import app; print('OK')"
```

## Commit Message
```
feat(scaffold): production-grade feature-modular project structure with external service isolation
```
