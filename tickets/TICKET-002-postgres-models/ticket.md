# TICKET-002: PostgreSQL Models & Migrations

**Branch:** `feature/TICKET-002-postgres-models`  
**Priority:** P0 — Required before TICKET-007 (trade persistence)  
**Estimate:** ~1.5h

## Summary
Define the async SQLAlchemy models, set up the Alembic migration toolchain, and create the `trades` table exactly as specified. All DB operations must be fully async.

## Scope

### Schema: `trades` Table
| Column | Type | Notes |
|---|---|---|
| id | UUID | PK, default uuid4 |
| instrument | VARCHAR | e.g. "NIFTY" |
| strike | INTEGER | ATM strike price |
| option_type | VARCHAR | "CE" or "PE" |
| side | VARCHAR | "LONG" or "SHORT" |
| entry_price | FLOAT | Simulated entry premium |
| pnl | FLOAT | Nullable initially, updated on close |
| signal_reason | TEXT | e.g. "+5.2% spike in 60s" |
| created_at | TIMESTAMP | UTC, auto now |
| notification_sent | BOOLEAN | default False — used by reconciliation |
| notification_sent_at | TIMESTAMP | Nullable |

> **Note:** `notification_sent` column is not in the spec but is critical for TICKET-009 reconciliation. Adding it proactively; will document in README.

### Files to Create/Modify
- `app/external/postgres/engine.py` — SQLAlchemy async engine, session factory, Base metadata
- `app/external/postgres/models.py` — `Trade` ORM model
- `app/core/dependencies.py` — async session dependency for FastAPI
- `app/external/postgres/migrations/env.py` — Alembic async config
- `app/external/postgres/migrations/versions/001_create_trades.py` — initial migration

### Connection Setup
- Use `asyncpg` driver: `postgresql+asyncpg://`
- Connection pool: min=2, max=10
- `create_async_engine` with `pool_pre_ping=True`

## Acceptance Criteria
- [ ] `alembic upgrade head` creates `trades` table successfully
- [ ] Can insert and retrieve a `Trade` record via async session
- [ ] Connection pool handles cold start (postgres not ready) with retry
- [ ] `notification_sent` boolean column present and defaults to False

## Dependencies
- TICKET-001 (project scaffold, docker-compose with postgres)

## Notes
- Use SQLAlchemy 2.x ORM with `DeclarativeBase`
- Use `uuid.uuid4` as default for id column
- Index `created_at` for time-range queries (AI layer, reconciliation)
- `notification_sent` index for efficient reconciliation query
