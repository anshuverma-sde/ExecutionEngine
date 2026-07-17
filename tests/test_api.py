"""Integration tests for the REST API using HTTPX + ASGITransport.

No live server, Redis, or Postgres is required — external dependencies are
stubbed at the FastAPI app.state level or via unittest.mock.
"""
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.router import api_router
from app.core.config import settings


# ── Minimal test app (no lifespan, no external services) ─────────────────────

def build_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)
    # Populate state fields that routes read
    app.state.settings = settings
    app.state.consumer = None
    return app


@pytest.fixture
def client():
    app = build_test_app()
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── /health ───────────────────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_status_ok(self, client):
        resp = client.get("/health")
        assert resp.json()["status"] == "ok"

    def test_feed_state_disabled_when_no_consumer(self, client):
        resp = client.get("/health")
        assert resp.json()["feed_state"] == "disabled"

    def test_environment_present(self, client):
        resp = client.get("/health")
        assert "environment" in resp.json()


# ── /metrics/latency ──────────────────────────────────────────────────────────

class TestLatencyMetrics:
    def test_returns_200(self, client):
        resp = client.get("/metrics/latency")
        assert resp.status_code == 200

    def test_has_required_fields(self, client):
        data = client.get("/metrics/latency").json()
        for field in ("p50_ms", "p95_ms", "p99_ms", "max_ms", "count", "sla_target_ms"):
            assert field in data, f"missing field: {field}"

    def test_sla_target_is_50ms(self, client):
        data = client.get("/metrics/latency").json()
        assert data["sla_target_ms"] == 50.0


# ── POST /metrics/reset ───────────────────────────────────────────────────────

class TestMetricsReset:
    def test_returns_200(self, client):
        resp = client.post("/metrics/reset")
        assert resp.status_code == 200

    def test_status_reset(self, client):
        assert client.post("/metrics/reset").json()["status"] == "reset"


# ── POST /debug/replay ────────────────────────────────────────────────────────

class TestReplayEndpoint:
    NDJSON = (
        b'{"security_id": "13", "ltp": 22000.0, "ts": "2026-01-01T09:30:00Z"}\n'
        b'{"security_id": "13", "ltp": 22010.0, "ts": "2026-01-01T09:30:01Z"}\n'
    )

    def test_returns_200_with_valid_ndjson(self, client):
        with patch("app.features.ingestion.pipeline.ingest_tick", new=AsyncMock(return_value=None)):
            resp = client.post(
                "/debug/replay",
                content=self.NDJSON,
                headers={"Content-Type": "application/x-ndjson"},
            )
        assert resp.status_code == 200

    def test_response_has_processed_count(self, client):
        with patch("app.features.ingestion.pipeline.ingest_tick", new=AsyncMock(return_value=None)):
            data = client.post(
                "/debug/replay",
                content=self.NDJSON,
                headers={"Content-Type": "application/x-ndjson"},
            ).json()
        assert data["processed"] == 2

    def test_skips_blank_lines(self, client):
        payload = b'{"security_id":"13","ltp":22000.0,"ts":"2026-01-01T09:30:00Z"}\n\n'
        with patch("app.features.ingestion.pipeline.ingest_tick", new=AsyncMock(return_value=None)):
            data = client.post(
                "/debug/replay",
                content=payload,
                headers={"Content-Type": "application/x-ndjson"},
            ).json()
        assert data["processed"] == 1

    def test_counts_errors_for_malformed_lines(self, client):
        payload = b"not-json\n"
        with patch("app.features.ingestion.pipeline.ingest_tick", new=AsyncMock(return_value=None)):
            data = client.post(
                "/debug/replay",
                content=payload,
                headers={"Content-Type": "application/x-ndjson"},
            ).json()
        assert data["errors"] >= 1


# ── GET /trades ───────────────────────────────────────────────────────────────

class TestTradesEndpoint:
    def test_returns_200_with_empty_db(self, client):
        mock_svc = AsyncMock()
        mock_svc.list_trades = AsyncMock(return_value=([], 0))

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with patch("app.features.trading.router.TradingService", return_value=mock_svc), \
             patch("app.core.dependencies.get_db", return_value=mock_db):
            resp = client.get("/trades")
        assert resp.status_code == 200

    def test_response_schema(self, client):
        mock_svc = AsyncMock()
        mock_svc.list_trades = AsyncMock(return_value=([], 0))

        with patch("app.features.trading.router.TradingService", return_value=mock_svc), \
             patch("app.core.dependencies.get_db", return_value=AsyncMock()):
            data = client.get("/trades").json()

        for field in ("items", "total", "page", "page_size"):
            assert field in data


# ── OpenAPI docs ──────────────────────────────────────────────────────────────

class TestOpenAPIDocs:
    def test_openapi_json_accessible(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200

    def test_openapi_has_paths(self, client):
        paths = client.get("/openapi.json").json()["paths"]
        assert "/health" in paths
        assert "/debug/replay" in paths
        assert "/metrics/latency" in paths
