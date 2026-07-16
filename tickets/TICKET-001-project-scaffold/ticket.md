# TICKET-001: Project Scaffold & DevOps Setup

**Branch:** `feature/TICKET-001-project-scaffold`  
**Priority:** P0 — Must be done first; all other tickets depend on this  
**Estimate:** ~2h

## Summary
Bootstrap the project with a production-grade, feature-modular folder structure. Each feature domain owns its own router/service/schema. Each external service gets its own isolated folder with all related files (client, config, schemas). No circular imports. Clean dependency direction: features → external services → core.

## Production-Grade Folder Structure

```
ExecutionEngine/
│
├── app/
│   ├── __init__.py
│   ├── main.py                         # FastAPI app, lifespan, middleware
│   │
│   ├── core/                           # Cross-cutting concerns (no business logic)
│   │   ├── __init__.py
│   │   ├── config.py                   # Pydantic BaseSettings (single source of truth)
│   │   ├── logging.py                  # Structured JSON logging setup
│   │   ├── exceptions.py               # Custom exception types
│   │   └── dependencies.py             # Shared FastAPI dependencies (e.g. get_db)
│   │
│   ├── external/                       # Third-party service clients (infrastructure layer)
│   │   ├── __init__.py
│   │   │
│   │   ├── dhanhq/                     # DhanHQ WebSocket feed
│   │   │   ├── __init__.py
│   │   │   ├── consumer.py             # WebSocket consumer, reconnect logic, watchdog
│   │   │   ├── schemas.py              # DhanHQ tick/message Pydantic schemas
│   │   │   └── config.py              # DhanHQ-specific settings (client_id, token)
│   │   │
│   │   ├── redis/                      # Redis client & rolling window
│   │   │   ├── __init__.py
│   │   │   ├── client.py               # Async connection pool, get_redis()
│   │   │   ├── window.py               # PriceWindow (ZSET-based 60s rolling window)
│   │   │   └── config.py              # Redis-specific settings (URL, DB indexes)
│   │   │
│   │   ├── postgres/                   # PostgreSQL / SQLAlchemy
│   │   │   ├── __init__.py
│   │   │   ├── engine.py               # Async engine, AsyncSessionLocal, Base
│   │   │   ├── models.py               # Trade ORM model
│   │   │   └── migrations/             # Alembic lives here (co-located with models)
│   │   │       ├── env.py
│   │   │       ├── script.py.mako
│   │   │       └── versions/
│   │   │           └── 001_create_trades.py
│   │   │
│   │   ├── celery/                     # Celery app, broker config, Beat schedule
│   │   │   ├── __init__.py
│   │   │   ├── app.py                  # Celery() instance, conf, beat_schedule
│   │   │   └── config.py              # Celery-specific settings (broker, backend)
│   │   │
│   │   ├── anthropic/                  # Claude API / LLM client
│   │   │   ├── __init__.py
│   │   │   ├── client.py               # AsyncAnthropic wrapper, agentic loop
│   │   │   └── config.py              # API key, model name settings
│   │   │
│   │   └── webhook/                    # Outbound notification provider
│   │       ├── __init__.py
│   │       ├── client.py               # HTTP client, send_notification()
│   │       └── config.py              # Webhook URL, timeout settings
│   │
│   ├── features/                       # Business feature modules (domain layer)
│   │   ├── __init__.py
│   │   │
│   │   ├── ingestion/                  # Feature: Tick ingestion pipeline
│   │   │   ├── __init__.py
│   │   │   ├── pipeline.py             # ingest_tick() — THE shared entry point
│   │   │   ├── service.py              # Ingestion orchestration
│   │   │   └── schemas.py              # Tick dataclass
│   │   │
│   │   ├── spike_detection/            # Feature: Spike detector
│   │   │   ├── __init__.py
│   │   │   ├── detector.py             # SpikeDetector class, detect()
│   │   │   ├── schemas.py              # Signal dataclass
│   │   │   └── cooldown.py             # Redis-backed cooldown logic
│   │   │
│   │   ├── trading/                    # Feature: Trade sim & persistence
│   │   │   ├── __init__.py
│   │   │   ├── router.py               # GET /trades, GET /trades/{id}
│   │   │   ├── service.py              # handle_signal(), create_trade()
│   │   │   ├── repository.py           # DB queries (async, thin layer)
│   │   │   ├── schemas.py              # TradeResponse Pydantic model
│   │   │   └── strike.py               # ATM strike calc, premium simulation
│   │   │
│   │   ├── notifications/              # Feature: Async notifications
│   │   │   ├── __init__.py
│   │   │   ├── tasks.py                # send_trade_notification Celery task
│   │   │   ├── reconciliation.py       # reconcile_notifications Beat task
│   │   │   └── schemas.py              # Notification payload schema
│   │   │
│   │   └── ai/                         # Feature: AI query layer
│   │       ├── __init__.py
│   │       ├── router.py               # POST /ask
│   │       ├── service.py              # answer_question(), tool dispatch
│   │       ├── mcp_server.py           # FastMCP server, 6 tool registrations
│   │       ├── tools.py                # Tool implementations (DB queries)
│   │       └── schemas.py              # AskRequest/AskResponse Pydantic models
│   │
│   ├── api/                            # API aggregation (routing only, no logic)
│   │   ├── __init__.py
│   │   ├── router.py                   # Aggregates all feature routers
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── health.py               # GET /health
│   │       ├── replay.py               # POST /debug/replay
│   │       └── metrics.py              # GET /metrics/latency
│   │
│   └── metrics/                        # Observability (no business logic)
│       ├── __init__.py
│       └── latency.py                  # LatencyCollector singleton
│
├── docker/                             # Dockerfiles for auxiliary services
│   └── webhook_mock/
│       ├── Dockerfile
│       └── server.py                   # Tiny FastAPI mock webhook server
│
├── scripts/
│   ├── generate_replay.py              # Generate NDJSON test file
│   └── benchmark.py                    # p50/p95/p99 benchmark runner
│
├── tests/
│   └── fixtures/
│       └── sample_replay.ndjson
│
├── alembic.ini                         # Points to app/external/postgres/migrations/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```

## Dependency Rules
```
core           ← imported by anyone
external/*     ← imported by features (never cross-import between external services)
features/*     ← imported by api, other features only via explicit service interfaces
api            ← imports feature routers only
metrics        ← imported by features (instrumentation)
```

## Files to Implement in This Ticket

### `app/core/config.py` — Pydantic BaseSettings
```python
class Settings(BaseSettings):
    # Grouped by service
    DATABASE_URL: str
    REDIS_URL: str
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str
    DHAN_CLIENT_ID: str = ""
    DHAN_ACCESS_TOKEN: str = ""
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-haiku-4-5-20251001"
    WEBHOOK_URL: str = "http://webhook-mock:8001/notify"
    LOG_LEVEL: str = "INFO"
```

### `app/main.py`
- FastAPI app with lifespan
- Startup: init Redis, DB engine, DhanHQ consumer, inject pipeline deps
- Register all routers
- GET /health

### `docker-compose.yml` Services
| Service | Image | Command |
|---|---|---|
| app | ./Dockerfile | uvicorn app.main:app |
| postgres | postgres:16 | — |
| redis | redis:7-alpine | — |
| celery-worker | ./Dockerfile | celery -A app.external.celery.app worker |
| celery-beat | ./Dockerfile | celery -A app.external.celery.app beat |
| webhook-mock | ./docker/webhook_mock | uvicorn server:app |

## Acceptance Criteria
- [ ] `docker compose up` starts all 6 services cleanly
- [ ] `GET /health` returns `{"status": "ok"}`
- [ ] All `__init__.py` files created (no implicit namespace packages)
- [ ] `.env.example` documents every setting
- [ ] No circular imports (verify with `python -c "from app.main import app"`)
- [ ] Celery app importable: `celery -A app.external.celery.app inspect ping`

## Notes
- Keep `app/main.py` lean — it wires things together, contains no logic
- All service config goes through `app/core/config.py` → injected into each external module
- `app/external/postgres/migrations/` lives next to `models.py` — keeps DB schema co-located with the model it describes
