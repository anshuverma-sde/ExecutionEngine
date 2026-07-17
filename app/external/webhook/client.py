"""Synchronous HTTP client for outbound webhook notifications.

Synchronous (not async) because Celery tasks run in a sync context.
Uses httpx sync client with a reasonable timeout.
"""
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_webhook_notification(payload: dict[str, Any]) -> None:
    """POST payload to the configured webhook URL.

    Raises httpx.HTTPError on failure — caller is responsible for retry logic.

    Args:
        payload: JSON-serialisable dict to POST.

    Raises:
        httpx.HTTPStatusError: Non-2xx response from the webhook endpoint.
        httpx.RequestError:    Network-level error (timeout, connection refused, etc.)
    """
    url = settings.WEBHOOK_URL
    timeout = settings.WEBHOOK_TIMEOUT_SECONDS

    logger.debug("Sending webhook to %s: %s", url, payload)

    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()

    logger.info("Webhook delivered to %s | status=%d", url, response.status_code)
