# Plan: TICKET-009 — Celery Beat Periodic Reconciliation

## Branch
```bash
git checkout -b feature/TICKET-009-celery-beat-reconciliation
```

## Implementation Steps

### Step 1 — `app/features/notifications/reconciliation.py`
```python
import logging
from datetime import datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.external.celery.app import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_sync_session():
    sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
    engine = create_engine(sync_url, pool_size=2)
    return Session(engine)


@celery_app.task(
    name="reconcile_notifications",
    max_retries=3,
    default_retry_delay=10,
    ignore_result=False,
)
def reconcile_notifications():
    """
    Periodic task (every 60s) to find trades without successful notifications
    and re-enqueue them. Safety net for broker failures and worker crashes.
    """
    from app.external.postgres.models import Trade
    from app.features.notifications.tasks import send_trade_notification
    
    cutoff = datetime.utcnow() - timedelta(minutes=2)
    
    try:
        with _get_sync_session() as db:
            unnotified = db.execute(
                select(Trade)
                .where(Trade.notification_sent == False)
                .where(Trade.notification_failed == False)  # skip permanent failures
                .where(Trade.created_at < cutoff)
                .order_by(Trade.created_at.asc())
                .limit(50)
            ).scalars().all()
    except Exception as e:
        logger.error(f"Reconciliation DB query failed: {e}")
        raise
    
    requeued = 0
    failed_enqueue = 0
    
    for trade in unnotified:
        try:
            send_trade_notification.apply_async(args=[str(trade.id)])
            requeued += 1
            logger.info(f"Reconciliation re-enqueued trade {trade.id}")
        except Exception as e:
            failed_enqueue += 1
            logger.error(f"Reconciliation failed to enqueue {trade.id}: {e}")
    
    summary = {
        "unnotified_found": len(unnotified),
        "requeued": requeued,
        "enqueue_failures": failed_enqueue,
        "ran_at": datetime.utcnow().isoformat(),
    }
    logger.info(f"Reconciliation complete: {summary}")
    return summary
```

### Step 2 — Update `app/external/celery/app.py` with Beat Schedule
```python
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    "reconcile-notifications": {
        "task": "reconcile_notifications",
        "schedule": 60.0,       # every 60 seconds
        "options": {
            "expires": 55,      # task expires if not picked up within 55s
                                # prevents pile-up if beat was paused/lagged
        },
    },
}

celery_app.conf.timezone = "UTC"
```

### Step 3 — Update `docker-compose.yml` Celery Beat Service
```yaml
celery-beat:
  build: .
  command: >
    celery -A app.external.celery.app beat
    --loglevel=info
    --pidfile=/tmp/celerybeat.pid
    --schedule=/tmp/celerybeat-schedule
  env_file: .env
  depends_on:
    redis:
      condition: service_healthy
    postgres:
      condition: service_healthy
  restart: unless-stopped
```

Note: Only one celery-beat instance should ever run. The `pidfile` and docker restart policy prevent duplicates.

### Step 4 — `GET /reconciliation/status` Endpoint (optional monitoring)
```python
# app/api/routes/metrics.py
@router.get("/reconciliation/status")
async def reconciliation_status(db: AsyncSession = Depends(get_db)):
    """Show count of trades pending notification."""
    from sqlalchemy import func, select
    from app.external.postgres.models import Trade
    
    cutoff = datetime.utcnow() - timedelta(minutes=2)
    result = await db.execute(
        select(func.count(Trade.id))
        .where(Trade.notification_sent == False)
        .where(Trade.notification_failed == False)
        .where(Trade.created_at < cutoff)
    )
    pending = result.scalar()
    
    failed_result = await db.execute(
        select(func.count(Trade.id))
        .where(Trade.notification_failed == True)
    )
    permanently_failed = failed_result.scalar()
    
    return {
        "pending_notifications": pending,
        "permanently_failed": permanently_failed,
    }
```

## Verification Steps
```bash
# 1. Simulate broker failure during a trade
# Stop Redis temporarily after a trade commit:
docker compose stop redis
# Wait for trade via replay, then restore Redis:
docker compose start redis
# Check that reconciliation picks up the missed notification within 60s:
docker compose logs celery-beat
docker compose logs celery-worker

# 2. Verify Beat fires every 60s
docker compose logs celery-beat | grep "reconcile"
# Should see entries every ~60 seconds

# 3. Check pending count
curl http://localhost:8000/reconciliation/status
# After successful notifications: {"pending_notifications": 0, "permanently_failed": 0}

# 4. Test permanent failure path
# Modify webhook mock to always return 500
# Let retries exhaust (may take ~15 minutes with full backoff)
# Check notification_failed=True in DB
docker compose exec postgres psql -U user -d engine \
  -c "SELECT id, notification_failed FROM trades WHERE notification_failed = TRUE;"
```

## Commit Message
```
feat: add Celery Beat reconciliation task for missed notifications
```
