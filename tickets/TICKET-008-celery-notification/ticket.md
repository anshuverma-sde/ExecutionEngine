# TICKET-008: Celery Notification Task

**Branch:** `feature/TICKET-008-celery-notification`  
**Priority:** P1 — Heavily weighted section  
**Estimate:** ~2.5h

## Summary
Implement the Celery notification task that fires after every successful trade commit. Requires: exponential backoff retries, max retry count with DLQ-style handling, and idempotency so the user never receives duplicate messages.

## Design Decisions

### Broker & Backend Choice
**Broker: Redis** (same Redis instance as rolling window, different DB index)
- Lower operational overhead vs RabbitMQ for this assignment
- Already in docker-compose
- Durability tradeoff: Redis without AOF/RDB risks message loss on crash — acceptable for assignment scope; RabbitMQ with mirrored queues would be the production choice

**Result Backend: Redis**
- Task results needed for reconciliation query (is notification done?)
- Alternative: PostgreSQL backend — avoids Redis dependency for results but adds latency; chose Redis for consistency

**Durability tradeoff accepted:** If the Redis broker crashes between Postgres commit and task enqueue, that notification is lost until the Celery Beat reconciliation (TICKET-009) picks it up. This is the intentional safety net.

### Notification Provider
**Mock HTTP webhook** — `POST http://webhook-mock:8001/notify` running as a Docker service.
- Provider is irrelevant per spec; delivery semantics matter
- Mock service allows controlled failure injection for testing

### Files to Create
- `app/external/celery/app.py` — Celery application instance
- `app/features/notifications/tasks.py` — `send_trade_notification` task
- `app/external/webhook/client.py` — webhook HTTP client

## Idempotency Mechanism

**Problem:** The same `trade_id` could be enqueued twice (replay, retry, reconciliation).  
**Solution:** Redis idempotency key

```python
IDEMPOTENCY_KEY = "notif_sent:{trade_id}"

@celery_app.task(
    bind=True,
    name="send_trade_notification",
    max_retries=5,
    default_retry_delay=60,
    acks_late=True,  # only ack after successful completion
)
def send_trade_notification(self, trade_id: str):
    key = f"notif_sent:{trade_id}"
    
    # Atomic check-and-set: returns 1 if key was newly set, 0 if already existed
    acquired = redis_client.set(key, "1", nx=True, ex=86400)  # 24h TTL
    if not acquired:
        logger.info(f"Notification already sent for trade {trade_id}, skipping")
        return {"status": "skipped", "reason": "duplicate"}
    
    try:
        trade = get_trade_sync(trade_id)  # sync DB read
        message = format_notification(trade)
        send_webhook(message)             # HTTP POST to provider
        mark_notification_sent(trade_id)  # UPDATE trades SET notification_sent=True
        return {"status": "sent", "trade_id": trade_id}
    except Exception as exc:
        redis_client.delete(key)          # release idempotency key on failure
        raise self.retry(
            exc=exc,
            countdown=2 ** self.request.retries * 30,  # 30s, 60s, 120s, 240s, 480s
            max_retries=5
        )
```

### After Max Retries
```python
@celery_app.task(name="notification_dead_letter")
def notification_dead_letter(trade_id: str, reason: str):
    """Called when all retries exhausted. Logs, alerts, marks for reconciliation."""
    logger.error(f"NOTIFICATION FAILED PERMANENTLY: trade={trade_id}, reason={reason}")
    # Mark in DB: notification_failed=True (add column in TICKET-002 migration)
    # Could also push to a Slack/email alert here
```

Link via `on_failure` callback or `link_error`:
```python
send_trade_notification.apply_async(
    args=[trade_id],
    link_error=notification_dead_letter.s(trade_id, "max_retries_exceeded")
)
```

## Notification Payload
```json
{"message": "Trade Alert! Long NIFTY 22450 CE entered at 14:05. Reason: +5.2% Spike."}
```

Format function:
```python
def format_notification(trade: Trade) -> str:
    time_str = trade.created_at.strftime("%H:%M")
    direction = "Long" if trade.side == "LONG" else "Short"
    return (
        f"Trade Alert! {direction} NIFTY {trade.strike} {trade.option_type} "
        f"entered at {time_str}. Reason: {trade.signal_reason}."
    )
```

## Failure Semantics (Part 4c Answers)

### Q1: Postgres commits, Celery broker unreachable
**What happens:** `send_trade_notification.delay()` raises `kombu.exceptions.OperationalError`. The trade is in Postgres but no task is enqueued.  
**What should happen:** The exception must be caught, logged as ERROR, and the trade marked with `notification_pending=True`. Celery Beat reconciliation (TICKET-009) will detect it within 60 seconds and re-enqueue.

```python
try:
    send_trade_notification.delay(str(trade.id))
except Exception as e:
    logger.error(f"Failed to enqueue notification for {trade.id}: {e}")
    # reconciliation will pick this up
```

### Q2: Worker sends message, crashes before ACK
**What happens:** With `acks_late=True`, the task is redelivered to another worker. The webhook receives the message twice.  
**What should happen:** The idempotency key (set before sending) survives the crash in Redis. On redelivery, `redis.set(key, nx=True)` returns 0 → task exits with "skipped". The duplicate is suppressed.  
**Why this works:** We set the idempotency key BEFORE the HTTP call. If the crash happens after HTTP but before ACK, the key exists → redelivery is a no-op. We accept "at most once notification" semantics within a task retry cycle.

### Q3: 200 spikes in 10 seconds, 4-worker pool
**What happens to ingestion:** Tick ingestion runs in FastAPI's async event loop (TICKET-004/005/006). Celery workers are separate processes. Ingestion is NOT blocked by notification workers.  
**What happens to latency:** Spike detection (Redis I/O) adds ~1-2ms per tick regardless of worker pool saturation. The tick-to-signal path never touches Celery.  
**What we did:** The pipeline is: tick → Redis → detect → signal. Celery enqueue (`delay()`) is a non-blocking Redis LPUSH. Even if 200 tasks queue up, the enqueue itself is < 1ms. Workers drain the queue asynchronously.

## Acceptance Criteria
- [ ] Task retries on HTTP failure with exponential backoff (30s, 60s, 120s, 240s, 480s)
- [ ] After 5 retries, `notification_dead_letter` is called (not silent failure)
- [ ] Duplicate `trade_id` enqueue → only one webhook call
- [ ] `notification_sent=True` set in DB after successful delivery
- [ ] `acks_late=True` configured (prevents loss on worker crash)
- [ ] Failure to enqueue (broker down) is caught and logged — not a 500 to caller

## Dependencies
- TICKET-001 (Celery in docker-compose, Redis)
- TICKET-002 (Trade model, notification_sent column)
- TICKET-007 (calls this task after commit)
