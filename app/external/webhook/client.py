"""Synchronous HTTP client for outbound webhook notifications.

Synchronous (not async) because Celery tasks run in a sync context.
Uses httpx sync client with a circuit breaker to fail-fast during outages.
"""
import logging
from typing import Any

import httpx

from app.core.config import settings
from app.external.webhook.circuit_breaker import CircuitBreaker, CircuitOpenError

logger = logging.getLogger(__name__)

# Process-level singleton — shared across all Celery tasks in this worker
_breaker = CircuitBreaker(
    threshold=settings.WEBHOOK_CIRCUIT_BREAKER_THRESHOLD,
    reset_after_seconds=settings.WEBHOOK_CIRCUIT_BREAKER_RESET_SECONDS,
)


def send_webhook_notification(payload: dict[str, Any]) -> None:
    """POST payload to the configured webhook URL.

    Raises httpx.HTTPError on failure — caller is responsible for retry logic.
    Raises CircuitOpenError if the circuit breaker has tripped.

    Args:
        payload: JSON-serialisable dict to POST.

    Raises:
        CircuitOpenError:      Webhook circuit is open; skip this attempt.
        httpx.HTTPStatusError: Non-2xx response from the webhook endpoint.
        httpx.RequestError:    Network-level error (timeout, connection refused).
    """
    url = settings.WEBHOOK_URL
    timeout = settings.WEBHOOK_TIMEOUT_SECONDS

    _breaker.before_call()   # raises CircuitOpenError if OPEN

    logger.debug("Sending webhook to %s: %s", url, payload)

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()

        _breaker.on_success()
        logger.info("Webhook delivered to %s | status=%d", url, response.status_code)

    except Exception as exc:
        _breaker.on_failure()
        raise exc


def webhook_circuit_status() -> dict:
    """Return circuit breaker status (used by /metrics/queue endpoint)."""
    return _breaker.status()
