"""Health check endpoint."""
from fastapi import APIRouter, Request

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(request: Request) -> dict:
    """
    System health check.

    Returns the application environment and current DhanHQ feed consumer state.
    """
    consumer = getattr(request.app.state, "consumer", None)
    return {
        "status": "ok",
        "environment": request.app.state.settings.ENVIRONMENT,
        "feed_state": getattr(consumer, "state", "disabled"),
    }
