"""Tiny FastAPI mock webhook server for local development and integration testing."""
import logging

from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webhook-mock")

app = FastAPI(title="Webhook Mock")


@app.post("/notify")
async def notify(request: Request) -> dict:
    """Accept and log incoming trade notifications."""
    body = await request.json()
    logger.info("[NOTIFICATION] %s", body.get("message", body))
    return {"status": "delivered"}


@app.get("/health")
async def health() -> dict:
    """Health check for the mock webhook server."""
    return {"status": "ok"}
