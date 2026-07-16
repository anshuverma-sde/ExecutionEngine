"""Latency metrics endpoint: GET /metrics/latency."""
from fastapi import APIRouter

router = APIRouter(tags=["observability"])


@router.get("/metrics/latency")
async def latency_metrics() -> dict:
    """
    Return p50/p95/p99 pipeline latency statistics.

    Implemented in TICKET-005 (observability & benchmarking).
    """
    pass
