# TICKET-009: Celery Beat Periodic Reconciliation

**Branch:** `feature/TICKET-009-celery-beat-reconciliation`  
**Priority:** P1 — Heavily weighted section  
**Estimate:** ~1.5h

## Summary
Configure Celery Beat to run a reconciliation task every 60 seconds. The task identifies trades in PostgreSQL that have no successful notification and re-enqueues them. This is the safety net for broker failures, worker crashes, and orphaned tasks.

## Reconciliation Question
> "Are there trades in Postgres that have no successful notification?"

Query:
```sql
SELECT id FROM trades
WHERE notification_sent = FALSE
  AND created_at < NOW() - INTERVAL '2 minutes'
ORDER BY created_at ASC
LIMIT 50;
```

**Why `created_at < NOW() - 2 minutes`:** New trades within 2 minutes may still have in-flight Celery tasks (retry backoff). Only consider trades old enough that all immediate retries should have completed.

**Why LIMIT 50:** Avoid overwhelming the worker pool if a large backlog accumulates.

## Celery Beat Configuration

```python
# app/external/celery/app.py
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    "reconcile-notifications": {
        "task": "reconcile_notifications",
        "schedule": 60.0,  # every 60 seconds
        "options": {"expires": 55},  # don't run stale task if Beat was paused
    }
}
```

## Reconciliation Task

```python
@celery_app.task(name="reconcile_notifications", max_retries=3)
def reconcile_notifications():
    """
    Find trades without successful notifications and re-enqueue them.
    Runs every 60 seconds via Celery Beat.
    """
    with SyncDBSession() as db:
        cutoff = datetime.utcnow() - timedelta(minutes=2)
        unnotified = db.execute(
            select(Trade)
            .where(Trade.notification_sent == False)
            .where(Trade.created_at < cutoff)
            .order_by(Trade.created_at)
            .limit(50)
        ).scalars().all()
    
    requeued = 0
    for trade in unnotified:
        try:
            # Idempotency key in TICKET-008 handles deduplication
            send_trade_notification.delay(str(trade.id))
            requeued += 1
        except Exception as e:
            logger.error(f"Reconciliation failed to enqueue {trade.id}: {e}")
    
    logger.info(f"Reconciliation: found {len(unnotified)} unnotified, requeued {requeued}")
    return {"unnotified": len(unnotified), "requeued": requeued}
```

## Failure Handling Strategy

### What if notification permanently fails?
1. `send_trade_notification` retries 5x with backoff
2. On max retries: `notification_dead_letter` fires, marks `notification_failed=True` in DB
3. Reconciliation skips `notification_failed=True` records (add to WHERE clause)
4. Admin can inspect `notification_failed` records and manually retry or escalate

```sql
-- Add to TICKET-002 migration
ALTER TABLE trades ADD COLUMN notification_failed BOOLEAN DEFAULT FALSE;
ALTER TABLE trades ADD COLUMN notification_failed_at TIMESTAMP;
ALTER TABLE trades ADD COLUMN notification_retry_count INTEGER DEFAULT 0;
```

### Why not retry forever?
Infinite retries mask bugs in the notification provider. A dead letter + alerting is the correct pattern. Reconciliation with a max attempt counter prevents infinite loops.

## Files to Create/Modify
- `app/features/notifications/reconciliation.py` — `reconcile_notifications` task
- `app/external/celery/app.py` — add beat_schedule config
- `docker-compose.yml` — `celery-beat` service (already in TICKET-001, populate here)

### Celery Beat Service (docker-compose)
```yaml
celery-beat:
  build: .
  command: celery -A app.external.celery.app beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
  # OR simpler:
  command: celery -A app.external.celery.app beat --loglevel=info
  depends_on:
    - redis
    - postgres
  env_file: .env
```

## Acceptance Criteria
- [ ] Beat task fires every 60 seconds (verifiable via logs)
- [ ] Trades created > 2 minutes ago with `notification_sent=False` are re-enqueued
- [ ] `notification_failed=True` trades are NOT re-enqueued by reconciliation
- [ ] Task logs count of unnotified/requeued per run
- [ ] Task does not crash if DB is temporarily unavailable (retries)
- [ ] Idempotency in TICKET-008 prevents double-notification when reconciliation re-enqueues

## Dependencies
- TICKET-001 (Celery Beat service in docker-compose)
- TICKET-002 (Trade model, notification_sent/failed columns)
- TICKET-008 (send_trade_notification task — called from reconciliation)
