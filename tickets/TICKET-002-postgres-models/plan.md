# Plan: TICKET-002 — PostgreSQL Models & Migrations

## Branch
```bash
git checkout main && git pull
git checkout -b feature/TICKET-002-postgres-models
```

## Implementation Steps

### Step 1 — `app/external/postgres/engine.py` (async engine + session)
```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

### Step 2 — `app/external/postgres/models.py`
```python
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Float, Text, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.external.postgres.engine import Base

class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    instrument: Mapped[str] = mapped_column(String(20))
    strike: Mapped[int] = mapped_column(Integer)
    option_type: Mapped[str] = mapped_column(String(2))   # CE or PE
    side: Mapped[str] = mapped_column(String(5))           # LONG or SHORT
    entry_price: Mapped[float] = mapped_column(Float)
    pnl: Mapped[float] = mapped_column(Float, default=0.0)
    signal_reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Notification tracking (for TICKET-008/009)
    notification_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    notification_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notification_failed: Mapped[bool] = mapped_column(Boolean, default=False)
    notification_retry_count: Mapped[int] = mapped_column(Integer, default=0)
```

### Step 3 — Alembic Initialization
```bash
# Run inside Docker or with venv
alembic init app/external/postgres/migrations
```

Edit `app/external/postgres/migrations/env.py`:
```python
from app.external.postgres.engine import Base
from app.external.postgres.models import Trade  # ensure models are imported
target_metadata = Base.metadata

# For async:
from sqlalchemy.ext.asyncio import create_async_engine
connectable = create_async_engine(config.get_main_option("sqlalchemy.url"))
```

Edit `alembic.ini`:
```ini
sqlalchemy.url = postgresql+asyncpg://user:pass@postgres:5432/engine
```
(Override from env in `env.py` using `os.environ.get("DATABASE_URL")`)

### Step 4 — Generate & Review Migration
```bash
alembic revision --autogenerate -m "create_trades_table"
# Review the generated file in app/external/postgres/migrations/versions/
alembic upgrade head
```

### Step 5 — Add DB Indexes
In the migration or model:
```python
from sqlalchemy import Index
# In Trade model:
__table_args__ = (
    Index("ix_trades_created_at", "created_at"),
    Index("ix_trades_notification_sent", "notification_sent"),
    Index("ix_trades_strike", "strike"),
)
```

### Step 6 — `app/core/dependencies.py` (FastAPI dependency)
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

## Verification
```bash
# Run migration
docker compose run --rm app alembic upgrade head

# Verify table created
docker compose exec postgres psql -U user -d engine -c "\d trades"
```

Expected columns: id, instrument, strike, option_type, side, entry_price, pnl, signal_reason, created_at, notification_sent, notification_sent_at, notification_failed, notification_retry_count

## Commit Message
```
feat: add async SQLAlchemy Trade model and Alembic migration
```
