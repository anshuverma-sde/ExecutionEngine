# Plan: TICKET-008 — Celery Notification Task

## Branch
```bash
git checkout -b feature/TICKET-008-celery-notification
```

## Implementation Steps

### Step 1 — `app/external/celery/app.py`
```python
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "execution_engine",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.features.notifications.tasks", "app.features.notifications.reconciliation"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,               # Only ack after task completes
    task_reject_on_worker_lost=True,   # Requeue if worker dies
    worker_prefetch_multiplier=1,      # One task at a time per worker (fair dispatch)
    task_track_started=True,
)
```

### Step 2 — `app/features/notifications/tasks.py`
```python
import json
import logging
from datetime import datetime

import httpx
import redis as sync_redis
from sqlalchemy import select, update
from celery import Task

from app.external.celery.app import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)

# Sync Redis client (Celery tasks are sync)
_redis = sync_redis.from_url(settings.REDIS_URL, decode_responses=True)


def _get_trade_sync(trade_id: str):
    """Synchronous DB read for Celery task context."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.external.postgres.models import Trade
    
    sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
    engine = create_engine(sync_url, pool_size=2)
    with Session(engine) as session:
        return session.get(Trade, trade_id)


def _mark_notification_sent(trade_id: str):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.external.postgres.models import Trade
    
    sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
    engine = create_engine(sync_url, pool_size=2)
    with Session(engine) as session:
        session.execute(
            update(Trade)
            .where(Trade.id == trade_id)
            .values(notification_sent=True, notification_sent_at=datetime.utcnow())
        )
        session.commit()


def _format_message(trade) -> str:
    time_str = trade.created_at.strftime("%H:%M")
    direction = "Long" if trade.side == "LONG" else "Short"
    return (
        f"Trade Alert! {direction} NIFTY {trade.strike} {trade.option_type} "
        f"entered at {time_str}. Reason: {trade.signal_reason}."
    )


@celery_app.task(
    bind=True,
    name="send_trade_notification",
    max_retries=5,
    acks_late=True,
)
def send_trade_notification(self, trade_id: str):
    """Send notification for a trade. Idempotent — safe to call multiple times."""
    
    # === IDEMPOTENCY CHECK ===
    idempotency_key = f"notif_sent:{trade_id}"
    acquired = _redis.set(idempotency_key, "1", nx=True, ex=86400)  # 24h TTL
    if not acquired:
        logger.info(f"Notification already sent for {trade_id}, skipping (idempotent)")
        return {"status": "skipped", "reason": "duplicate", "trade_id": trade_id}
    
    try:
        # Fetch trade
        trade = _get_trade_sync(trade_id)
        if not trade:
            logger.error(f"Trade {trade_id} not found in DB")
            _redis.delete(idempotency_key)
            return {"status": "error", "reason": "trade_not_found"}
        
        message = _format_message(trade)
        payload = {"message": message, "trade_id": trade_id}
        
        # Send notification
        with httpx.Client(timeout=10.0) as client:
            response = client.post(settings.WEBHOOK_URL, json=payload)
            response.raise_for_status()
        
        # Mark as sent in DB
        _mark_notification_sent(trade_id)
        logger.info(f"Notification sent for trade {trade_id}")
        return {"status": "sent", "trade_id": trade_id}
    
    except httpx.HTTPStatusError as exc:
        _redis.delete(idempotency_key)  # Release on failure
        logger.warning(f"HTTP error sending notification for {trade_id}: {exc}")
        countdown = 30 * (2 ** self.request.retries)  # 30s, 60s, 120s, 240s, 480s
        raise self.retry(exc=exc, countdown=countdown)
    
    except Exception as exc:
        _redis.delete(idempotency_key)
        logger.error(f"Unexpected error for {trade_id}: {exc}")
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


@celery_app.task(name="notification_dead_letter")
def notification_dead_letter(trade_id: str, reason: str = "max_retries_exceeded"):
    """Called when all retries for a notification are exhausted."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.external.postgres.models import Trade
    
    logger.error(
        f"NOTIFICATION PERMANENTLY FAILED: trade={trade_id}, reason={reason}. "
        "Manual intervention required."
    )
    
    sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
    engine = create_engine(sync_url)
    with Session(engine) as session:
        session.execute(
            update(Trade)
            .where(Trade.id == trade_id)
            .values(notification_failed=True)
        )
        session.commit()
```

### Step 3 — Enqueue with Dead Letter Link
In `app/features/trading/service.py`, update `_enqueue_notification`:
```python
def _enqueue_notification(trade_id: str):
    try:
        from app.features.notifications.tasks import send_trade_notification, notification_dead_letter
        send_trade_notification.apply_async(
            args=[trade_id],
            link_error=notification_dead_letter.s(trade_id),
        )
    except Exception as e:
        logger.error(f"Failed to enqueue notification for {trade_id}: {e}")
```

### Step 4 — Webhook Mock Service
`Dockerfile.webhook`:
```dockerfile
FROM python:3.12-slim
RUN pip install fastapi uvicorn
COPY webhook_mock.py .
CMD ["uvicorn", "webhook_mock:app", "--host", "0.0.0.0", "--port", "8001"]
```

`webhook_mock.py`:
```python
import logging
from fastapi import FastAPI, Request

app = FastAPI()
logger = logging.getLogger(__name__)

@app.post("/notify")
async def notify(request: Request):
    body = await request.json()
    logger.info(f"NOTIFICATION RECEIVED: {body['message']}")
    return {"status": "delivered", "message": body["message"]}
```

### Step 5 — Add psycopg2 to requirements
```
psycopg2-binary==2.9.9   # sync driver for Celery tasks
```

## Verification
```bash
# Trigger a trade via replay
curl -X POST http://localhost:8000/debug/replay \
  --data-binary @tests/sample_replay.ndjson \
  ?reset_window=true

# Check Celery worker logs for task execution
docker compose logs celery-worker

# Check webhook mock logs for delivery
docker compose logs webhook-mock

# Verify DB update
docker compose exec postgres psql -U user -d engine \
  -c "SELECT id, notification_sent, notification_sent_at FROM trades LIMIT 5;"
```

## Commit Message
```
feat: add Celery notification task with exponential backoff, idempotency, and dead letter
```
