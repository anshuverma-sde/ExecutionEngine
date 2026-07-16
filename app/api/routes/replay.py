"""Replay endpoint for debugging: POST /debug/replay."""
from fastapi import APIRouter

router = APIRouter(tags=["debug"])


@router.post("/debug/replay")
async def replay() -> dict:
    """
    Replay a recorded NDJSON tick file through the ingestion pipeline.

    Implemented in TICKET-005 (benchmark & replay tooling).
    """
    pass
