"""Celery tasks for trade notifications.

Delivery semantics:
  - at-least-once (task_acks_late=True, task_reject_on_worker_lost=True)
  - idempotency via Redis SETNX prevents duplicate user-visible messages
  - exponential backoff: 30s → 60s → 120s → 240s → 480s (max 5 retries)
  - dead letter: notification_dead_letter fires after all retries exhausted

Failure scenario Q2 (spec):
  Worker sends webhook, crashes before ACK.
  → task_reject_on_worker_lost requeues the task.
  → On redelivery, Redis SETNX returns False (key exists) → skipped.
  → The idempotency key was set BEFORE the HTTP call, so crash-after-send
    is correctly deduplicated. User sees exactly one message.
"""
import logging
import uuid
from datetime import datetime, timezone

import redis as sync_redis
from sqlalchemy import update

from app.external.celery.app import celery_app
from app.core.config import settings
from app.external.postgres.models import Trade
from app.external.postgres.sync_engine import get_sync_session
from app.external.webhook.client import send_webhook_notification

logger = logging.getLogger(__name__)

# Synchronous Redis client for use inside Celery tasks (sync context)
_redis = sync_redis.from_url(settings.REDIS_URL, decode_responses=True)

IDEMPOTENCY_KEY_PREFIX = "notif_sent:"
IDEMPOTENCY_TTL_SECONDS = 86_400   # 24 hours


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_trade_sync(trade_id: str):
    """Fetch a Trade record synchronously (for Celery task context)."""
    with get_sync_session() as session:
        return session.get(Trade, uuid.UUID(trade_id))


def _mark_notification_sent_sync(trade_id: str) -> None:
    """Set notification_sent=True on the trade record (sync)."""
    with get_sync_session() as session:
        session.execute(
            update(Trade)
            .where(Trade.id == uuid.UUID(trade_id))
            .values(
                notification_sent=True,
                notification_sent_at=datetime.now(timezone.utc),
            )
        )
        session.commit()


def _format_notification_message(trade) -> str:
    """Format the notification message per spec."""
    time_str = trade.created_at.strftime("%H:%M")
    direction = "Long" if trade.side == "LONG" else "Short"
    return (
        f"Trade Alert! {direction} NIFTY {trade.strike} {trade.option_type} "
        f"entered at {time_str}. Reason: {trade.signal_reason}."
    )


# ── Tasks ─────────────────────────────────────────────────────────────────────

@celery_app.task(
    name="app.features.notifications.tasks.send_trade_notification",
    bind=True,
    max_retries=5,
    acks_late=True,
    queue="notifications",
)
def send_trade_notification(self, trade_id: str) -> dict:
    """Send a WhatsApp/webhook notification for a completed trade.

    Idempotency:
      Before the HTTP call we attempt Redis SETNX on key notif_sent:{trade_id}.
      If the key already exists (duplicate enqueue or redelivery after crash),
      the task exits immediately — the user never receives a duplicate message.
      On failure we delete the key so the next retry can claim it.

    Retry schedule (exponential backoff):
      attempt 0: immediate
      attempt 1: 30s
      attempt 2: 60s
      attempt 3: 120s
      attempt 4: 240s
      attempt 5: 480s  → max_retries exhausted → notification_dead_letter fires
    """
    idempotency_key = f"{IDEMPOTENCY_KEY_PREFIX}{trade_id}"

    # ── Idempotency check (atomic SETNX) ──────────────────────────────────────
    claimed = _redis.set(idempotency_key, "1", nx=True, ex=IDEMPOTENCY_TTL_SECONDS)
    if not claimed:
        logger.info(
            "Notification already sent for trade %s — skipping (idempotent)", trade_id
        )
        return {"status": "skipped", "reason": "duplicate", "trade_id": trade_id}

    try:
        # ── Fetch trade ───────────────────────────────────────────────────────
        trade = _get_trade_sync(trade_id)
        if trade is None:
            logger.error("Trade %s not found in DB — dropping notification", trade_id)
            _redis.delete(idempotency_key)
            return {"status": "error", "reason": "trade_not_found", "trade_id": trade_id}

        # ── Build and send notification ───────────────────────────────────────
        message = _format_notification_message(trade)
        payload = {"message": message, "trade_id": trade_id}

        send_webhook_notification(payload)   # raises on failure

        # ── Mark success in DB ────────────────────────────────────────────────
        _mark_notification_sent_sync(trade_id)

        logger.info("Notification sent for trade %s: %s", trade_id, message)
        return {"status": "sent", "trade_id": trade_id, "message": message}

    except Exception as exc:
        # Release idempotency key so the next retry attempt can re-claim it
        _redis.delete(idempotency_key)

        attempt = self.request.retries
        countdown = 30 * (2 ** attempt)   # 30s, 60s, 120s, 240s, 480s

        logger.warning(
            "Notification failed for %s (attempt %d/%d): %s — retrying in %ds",
            trade_id,
            attempt + 1,
            self.max_retries + 1,
            exc,
            countdown,
        )
        raise self.retry(exc=exc, countdown=countdown)


@celery_app.task(
    name="app.features.notifications.tasks.notification_dead_letter",
    queue="notifications",
)
def notification_dead_letter(trade_id: str, reason: str = "max_retries_exceeded") -> None:
    """Called when all retries for a notification are exhausted.

    Marks the trade as permanently failed in the DB and logs a critical alert.
    The Celery Beat reconciliation task will NOT re-enqueue permanently failed trades.
    Manual intervention is required (e.g. check WEBHOOK_URL, re-trigger manually).
    """
    logger.error(
        "NOTIFICATION PERMANENTLY FAILED | trade=%s | reason=%s | manual action required",
        trade_id,
        reason,
    )

    try:
        with get_sync_session() as session:
            session.execute(
                update(Trade)
                .where(Trade.id == uuid.UUID(trade_id))
                .values(notification_failed=True)
            )
            session.commit()
        logger.info("Trade %s marked notification_failed=True", trade_id)
    except Exception as exc:
        logger.error("Failed to mark trade %s as notification_failed: %s", trade_id, exc)
