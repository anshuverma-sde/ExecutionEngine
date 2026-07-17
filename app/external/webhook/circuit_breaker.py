"""Simple in-process circuit breaker for the webhook notification client.

States:
  CLOSED  — normal operation; requests flow through
  OPEN    — fail-fast; no requests attempted until reset_after_seconds elapses
  HALF_OPEN — one probe request allowed; success → CLOSED, failure → OPEN

This prevents Celery workers from burning through retries and blocking for
15 minutes when the webhook endpoint is down for an extended period.

Usage:
    breaker = CircuitBreaker(threshold=5, reset_after_seconds=60)

    try:
        breaker.before_call()          # raises CircuitOpenError if OPEN
        send_webhook_notification(...)
        breaker.on_success()
    except CircuitOpenError:
        raise                          # let Celery handle as a retry
    except Exception:
        breaker.on_failure()
        raise
"""
import logging
import time
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when a call is attempted while the circuit is OPEN."""


class CircuitBreaker:
    """Thread-safe (GIL-protected) circuit breaker for sync Celery task context."""

    def __init__(self, threshold: int = 5, reset_after_seconds: int = 60) -> None:
        self._threshold = threshold
        self._reset_after = reset_after_seconds
        self._failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at: float = 0.0

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._opened_at >= self._reset_after:
                self._state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker → HALF_OPEN (probe allowed)")
        return self._state

    def before_call(self) -> None:
        """Call before attempting the webhook. Raises CircuitOpenError if open."""
        if self.state == CircuitState.OPEN:
            raise CircuitOpenError(
                f"Webhook circuit is OPEN — skipping call "
                f"(resets in {self._reset_after - (time.monotonic() - self._opened_at):.0f}s)"
            )

    def on_success(self) -> None:
        """Record a successful call — reset failure count and close the circuit."""
        if self._state != CircuitState.CLOSED:
            logger.info("Circuit breaker → CLOSED after successful probe")
        self._failures = 0
        self._state = CircuitState.CLOSED

    def on_failure(self) -> None:
        """Record a failed call — trip the circuit after threshold consecutive failures."""
        self._failures += 1
        if self._state == CircuitState.HALF_OPEN or self._failures >= self._threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            logger.error(
                "Circuit breaker → OPEN after %d consecutive failures "
                "(auto-reset in %ds)",
                self._failures,
                self._reset_after,
            )
        else:
            logger.warning(
                "Webhook failure %d/%d — circuit still CLOSED",
                self._failures,
                self._threshold,
            )

    def status(self) -> dict:
        """Return current breaker status for observability endpoints."""
        return {
            "state": self.state.value,
            "consecutive_failures": self._failures,
            "threshold": self._threshold,
            "reset_after_seconds": self._reset_after,
        }
