# Instant Strike Execution Engine

A low-latency NIFTY 50 options execution engine that ingests a live market feed, detects rapid price movements, simulates option trades, persists them durably, dispatches notifications asynchronously, and exposes an AI-powered query layer over the results.

**Hard SLA: p99 tick-to-signal latency < 50ms**

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Local Development Setup](#local-development-setup)
3. [Production Setup](#production-setup)
4. [Configuration Reference](#configuration-reference)
5. [Testing Notifications](#testing-notifications)
6. [API Reference](#api-reference)
7. [Design Decisions](#design-decisions)
8. [Failure Semantics](#failure-semantics)
9. [Running the Benchmark](#running-the-benchmark)

---

## System Architecture

```
Market Feed ──► [Ingestion] ──► [Spike Detector] ──► [Execution Sim]
   (WS)              │                  │                    │
                   Redis              Redis            [Postgres Commit]
                                                            │
                                                    [Celery Task Queue]
                                                      │             │
                                                 [Notification]  [Beat]
                                                              ▲
                                               [AI / MCP Layer] ◄── reads Postgres + Redis
```

### Architecture Flow (Mermaid)

```mermaid
flowchart TD
    subgraph Feed["Market Feed"]
        WS["DhanHQ WebSocket\nNIFTY 50 · Security ID 13"]
        REPLAY["POST /debug/replay\nNDJSON tick file"]
    end

    subgraph Ingestion["Ingestion Pipeline"]
        WINDOW["PriceWindow\nRedis Sorted Set\n60s rolling window"]
        DETECTOR["SpikeDetector\n+-5pct over 60s\nLONG or SHORT"]
        COOLDOWN["CooldownManager\nRedis SETNX\n60s per-security"]
        LATENCY["LatencyCollector\np50 / p95 / p99"]
    end

    subgraph Execution["Order Simulation"]
        ATM["ATM Strike\nnearest 50 increment"]
        PREMIUM["Premium Simulation\nintrinsic + time value"]
        DB[("PostgreSQL\ntrades table")]
    end

    subgraph Async["Async Work - Celery"]
        QUEUE["Redis Broker\nnotifications queue"]
        WORKER["Celery Worker\nexponential backoff\nidempotency via SETNX"]
        BEAT["Celery Beat\nreconcile every 60s"]
        WEBHOOK["Webhook / WhatsApp\nHTTP POST"]
    end

    subgraph AI["AI Query Layer"]
        ASK["POST /ask\nnatural language"]
        MCP["MCP Tools\nget_last_trade\nget_open_positions\nget_pnl_summary\nget_spike_events\nget_best_strike_accuracy\ngenerate_trade_chart"]
        LLM["LLM Provider\nGroq / OpenAI / Ollama"]
    end

    WS -->|tick| WINDOW
    REPLAY -->|tick| WINDOW
    WINDOW -->|"60s baseline price"| DETECTOR
    DETECTOR --> COOLDOWN
    COOLDOWN -->|signal| ATM
    DETECTOR --> LATENCY
    ATM --> PREMIUM
    PREMIUM --> DB
    DB -->|trade_id| QUEUE
    QUEUE --> WORKER
    WORKER --> WEBHOOK
    BEAT -->|"re-enqueue unnotified"| QUEUE
    DB -.->|reads| MCP
    WINDOW -.->|reads| MCP
    ASK --> LLM
    LLM --> MCP
```

### Component Breakdown

| Component | Technology | Role |
|---|---|---|
| WebSocket Consumer | DhanHQ `dhanhq` library | Subscribes to NIFTY 50 LTP feed (Security ID 13) |
| Ingestion Pipeline | FastAPI + asyncio | Single entry point `ingest_tick()` shared by WS and replay |
| Rolling Window | Redis Sorted Sets | 60-second price window per security, O(log N) append |
| Spike Detector | Pure Python | ±5% move over 60s triggers LONG (CE) or SHORT (PE) signal |
| Cooldown Guard | Redis SETNX | 60-second per-security cooldown prevents signal storms |
| Order Simulator | Python | ATM strike selection + premium simulation, persisted to Postgres |
| Notification | Celery + Redis | Webhook/WhatsApp delivery with idempotency, retry, dead letter |
| Reconciliation | Celery Beat | Every 60s: re-enqueues trades with no successful notification |
| AI Query Layer | FastAPI + Groq/OpenAI/Ollama | Natural-language queries over live trade data via MCP tools |

### Folder Structure

```
app/
├── core/               # Config, logging, shared dependencies
├── api/                # FastAPI router aggregation
│   └── routes/         # health, replay, metrics
├── external/           # All third-party service clients (isolated)
│   ├── dhanhq/         # WebSocket consumer + reconnect logic
│   ├── redis/          # Async Redis client, rolling window, cooldown
│   ├── postgres/       # SQLAlchemy engine, models, Alembic migrations
│   ├── celery/         # Celery app config + Beat schedule
│   ├── llm/            # Provider-agnostic LLM layer (Groq/OpenAI/Ollama)
│   └── webhook/        # Sync HTTP client for outbound notifications
├── features/           # Business logic, feature-modular
│   ├── ingestion/      # ingest_tick() pipeline + schemas
│   ├── spike_detection/ # SpikeDetector, CooldownManager
│   ├── trading/        # ATM strike, order sim, repository, API router
│   ├── notifications/  # Celery tasks, reconciliation
│   └── ai/             # MCP server, 6 tools, POST /ask
└── metrics/            # LatencyCollector singleton
```

---

## Local Development Setup

### Prerequisites

- Python 3.10+
- PostgreSQL 14+ running locally
- Redis 7+ running locally
- `virtualenv` (`pip install virtualenv`)
- A free Groq API key — [console.groq.com](https://console.groq.com)

**Install Redis (if not installed):**
```bash
# Ubuntu / Debian
sudo apt install redis-server
sudo systemctl start redis

# macOS
brew install redis
brew services start redis

# Verify
redis-cli ping   # → PONG
```

**Install PostgreSQL (if not installed):**
```bash
# Ubuntu / Debian
sudo apt install postgresql
sudo systemctl start postgresql

# macOS
brew install postgresql@16
brew services start postgresql@16

# Verify
psql --version
```

### Step 1 — Clone the repository

```bash
git clone https://github.com/anshuverma-sde/ExecutionEngine.git
cd ExecutionEngine
```

### Step 2 — Create and activate virtual environment

```bash
pip install virtualenv
virtualenv venv
source venv/bin/activate      # Linux / macOS
# venv\Scripts\activate       # Windows
```

> All subsequent commands assume the venv is active. If you open a new terminal, run `source venv/bin/activate` again.

### Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

### Step 4 — Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

```env
# Database (uses your local Postgres)
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=postgres
DB_NAME=engine

# Redis (local)
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# AI — get a free key at https://console.groq.com
GROQ_API_KEY=gsk_...

# Optional: DhanHQ live feed (leave empty to use replay-only mode)
DHAN_CLIENT_ID=
DHAN_ACCESS_TOKEN=
```

### Step 5 — Create the database and run migrations

```bash
# Create the database (run once)
PGPASSWORD=postgres createdb -U postgres -h localhost engine

# Apply all schema migrations
alembic upgrade head

# Verify migration status
alembic current

# View full migration history
alembic history --verbose
```

### Step 6 — Start the FastAPI server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API docs available at: `http://localhost:8000/docs` (Swagger UI)

### Step 7 — Start Celery worker (separate terminal)

```bash
source venv/bin/activate
celery -A app.external.celery.app worker \
  --loglevel=info \
  --concurrency=4 \
  --queues=notifications,reconciliation,default
```

### Step 8 — Start Celery Beat scheduler (separate terminal)

```bash
source venv/bin/activate
celery -A app.external.celery.app beat --loglevel=info
```

### Step 9 — Verify everything is running

```bash
# Health check
curl http://localhost:8000/health
# {"status": "ok", "environment": "development"}

# Run a replay to generate a trade (reset window so spike fires)
curl -X POST "http://localhost:8000/debug/replay?reset_window=true&reset_metrics=true" \
  -H "Content-Type: application/x-ndjson" \
  --data-binary @tests/fixtures/sample_replay.ndjson

# Check the trade was persisted
curl http://localhost:8000/trades

# Get a single trade by UUID
curl http://localhost:8000/trades/<trade-id-from-above>

# Check latency SLA
curl http://localhost:8000/metrics/latency

# Reset latency samples (before a clean benchmark run)
curl -X POST http://localhost:8000/metrics/reset

# Check reconciliation status
curl http://localhost:8000/reconciliation/status

# Ask the AI a question (requires GROQ_API_KEY in .env)
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What was the last trade?"}'

curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Compare CE vs PE profitability."}'

curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Is the p99 latency SLA being met?"}'
```

### Optional: Run the benchmark

```bash
# Basic run (uses sample_replay.ndjson, 120 ticks)
python scripts/benchmark.py

# Reset the price window so the spike fires on every run
python scripts/benchmark.py --reset-window

# Custom file and server URL
python scripts/benchmark.py \
  --file tests/fixtures/sample_replay.ndjson \
  --url http://localhost:8000

# Generate a larger fixture first (500 ticks, spike at tick 65)
python scripts/generate_replay.py \
  --ticks 500 \
  --out tests/fixtures/large_replay.ndjson
python scripts/benchmark.py --file tests/fixtures/large_replay.ndjson

# Machine-readable JSON output (exit 0 = SLA met, exit 1 = SLA breached)
python scripts/benchmark.py --json
```

### Useful Alembic commands

```bash
# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Rollback all migrations
alembic downgrade base

# Show current revision
alembic current

# Show history
alembic history --verbose

# Auto-generate a new migration after model changes
alembic revision --autogenerate -m "describe your change"
```

---

## Production Setup

### Prerequisites

- Docker 24+ and Docker Compose v2
- A server with at least 2 CPU cores and 4 GB RAM
- Domain name (optional, for HTTPS)
- Groq/OpenAI API key
- DhanHQ credentials for live feed

### Step 1 — Clone the repository

```bash
git clone https://github.com/anshuverma-sde/ExecutionEngine.git
cd ExecutionEngine
```

### Step 2 — Configure environment

```bash
cp .env.example .env
```

Edit `.env` for production:

```env
# Database — use a managed Postgres service or Docker volume
DB_HOST=postgres        # Docker service name (or your managed DB host)
DB_PORT=5432
DB_USER=engine_user
DB_PASSWORD=<strong-password>
DB_NAME=engine

# OR set the full URL directly (takes precedence over DB_* vars)
# DATABASE_URL=postgresql+asyncpg://engine_user:<password>@your-db-host:5432/engine

# Redis — Docker service name or managed Redis
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# DhanHQ live feed credentials
DHAN_CLIENT_ID=your_client_id
DHAN_ACCESS_TOKEN=your_access_token

# AI provider
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile

# Notification webhook (your WhatsApp/Twilio endpoint)
WEBHOOK_URL=https://your-webhook-endpoint.com/notify
WEBHOOK_TIMEOUT_SECONDS=10

# App
LOG_LEVEL=INFO
ENVIRONMENT=production
```

### Step 3 — Build and start all services

```bash
docker compose up --build -d
```

This starts:
| Service | Description |
|---|---|
| `postgres` | PostgreSQL 16 database with persistent volume |
| `redis` | Redis 7 for price window, cooldown, and Celery |
| `app` | FastAPI server on port 8000 |
| `celery-worker` | 4-process Celery worker (notifications + reconciliation) |
| `celery-beat` | Celery Beat scheduler (reconciliation every 60s) |
| `webhook-mock` | Mock webhook receiver on port 8001 (remove in prod) |

### Step 4 — Run database migrations

```bash
docker compose exec app alembic upgrade head
```

### Step 5 — Verify all containers are healthy

```bash
docker compose ps
```

All services should show `healthy` or `running`. Then:

```bash
curl http://localhost:8000/health
# {"status": "ok", "environment": "production"}
```

### Step 6 — (Optional) Set up a reverse proxy with HTTPS

Use Nginx or Caddy in front of port 8000. Example Nginx config:

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate     /etc/ssl/certs/your-cert.pem;
    ssl_certificate_key /etc/ssl/private/your-key.pem;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_read_timeout 60s;
    }
}
```

### Step 7 — Monitor logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f app
docker compose logs -f celery-worker
docker compose logs -f celery-beat
```

### Step 8 — Scaling workers (if needed)

```bash
# Run 2 Celery worker containers
docker compose up --scale celery-worker=2 -d
```

### Updating to a new version

```bash
git pull origin main
docker compose build
docker compose up -d
docker compose exec app alembic upgrade head   # run if there are new migrations
```

### Stopping all services

```bash
docker compose down           # stop containers, keep volumes
docker compose down -v        # stop and DELETE all data (destructive)
```

---

## Configuration Reference

All configuration is via environment variables. Two styles are supported:

**Option A — Individual DB vars (recommended for local dev):**
```env
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=postgres
DB_NAME=engine
```

**Option B — Full connection URL (overrides Option A, recommended for production/cloud):**
```env
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname
```

### Full variable reference

| Variable | Default | Description |
|---|---|---|
| `DB_HOST` | `localhost` | Postgres host |
| `DB_PORT` | `5432` | Postgres port |
| `DB_USER` | `postgres` | Postgres user |
| `DB_PASSWORD` | `postgres` | Postgres password |
| `DB_NAME` | `engine` | Postgres database name |
| `DATABASE_URL` | _(empty)_ | Full async URL — overrides DB_* vars when set |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis (price window + cooldown) |
| `CELERY_BROKER_URL` | `redis://localhost:6379/1` | Celery task broker |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/2` | Celery result store |
| `DHAN_CLIENT_ID` | _(empty)_ | DhanHQ client ID (omit to disable live feed) |
| `DHAN_ACCESS_TOKEN` | _(empty)_ | DhanHQ access token |
| `LLM_PROVIDER` | `groq` | AI provider: `groq` \| `openai` \| `ollama` |
| `GROQ_API_KEY` | _(empty)_ | Groq API key — [console.groq.com](https://console.groq.com) |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model |
| `OPENAI_API_KEY` | _(empty)_ | OpenAI API key (when `LLM_PROVIDER=openai`) |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL (when `LLM_PROVIDER=ollama`) |
| `OLLAMA_MODEL` | `llama3.2` | Ollama model |
| `WEBHOOK_URL` | `http://localhost:8001/notify` | Notification delivery endpoint |
| `WEBHOOK_TIMEOUT_SECONDS` | `10` | HTTP timeout for outbound notifications |
| `LOG_LEVEL` | `INFO` | Logging level: DEBUG \| INFO \| WARNING \| ERROR |
| `ENVIRONMENT` | `development` | Environment label |

**Switching AI providers — no code changes needed:**
```bash
LLM_PROVIDER=groq    GROQ_API_KEY=gsk_...         # Free, recommended
LLM_PROVIDER=openai  OPENAI_API_KEY=sk-...         # GPT-4o-mini
LLM_PROVIDER=ollama  OLLAMA_BASE_URL=http://...    # Local, zero cost
```

---

## Testing Notifications

Notifications are delivered as HTTP POST requests to `WEBHOOK_URL` with this payload:

```json
{"message": "Trade Alert! Long NIFTY 22450 CE entered at 14:05. Reason: +5.23% spike in 60s."}
```

### Option A — webhook.site (easiest, no setup)

1. Open [https://webhook.site](https://webhook.site) in your browser — copy the unique URL shown
2. Set it in your `.env`:
   ```
   WEBHOOK_URL=https://webhook.site/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ```
3. Restart the app, trigger a replay — notifications appear live in the browser

### Option B — local mock server (one-liner)

Run this in a separate terminal before starting the app:

```bash
python3 -c "
from http.server import HTTPServer, BaseHTTPRequestHandler
import json, datetime

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        print(f'[{datetime.datetime.now().strftime(\"%H:%M:%S\")}] NOTIFICATION:', json.loads(body)['message'])
        self.send_response(200); self.end_headers()
    def log_message(self, *a): pass

print('Listening on http://localhost:8001/notify ...')
HTTPServer(('', 8001), H).serve_forever()
"
```

Keep `WEBHOOK_URL=http://localhost:8001/notify` in `.env` (the default). Every trade notification prints instantly to this terminal.

### Option C — check notification status via API

```bash
# See how many trades are pending notification
curl http://localhost:8000/reconciliation/status

# notification_sent field per trade
curl http://localhost:8000/trades
```

### Triggering a notification end-to-end

```bash
# 1. Start the mock server (Option B above)

# 2. Run the replay with window reset so a spike fires
curl -X POST "http://localhost:8000/debug/replay?reset_window=true" \
  -H "Content-Type: application/x-ndjson" \
  --data-binary @tests/fixtures/sample_replay.ndjson

# 3. Watch the mock server terminal — notification arrives within seconds
# [14:05:32] NOTIFICATION: Trade Alert! Long NIFTY 22450 CE entered at 14:05. Reason: +5.23% spike in 60s.
```

---

## API Reference

### Health

#### `GET /health`
```json
{"status": "ok", "environment": "development"}
```

---

### Trades

#### `GET /trades`
Paginated list of all recorded trades, newest first.

**Query params:** `page` (default 1), `page_size` (default 20, max 100)

```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "instrument": "NIFTY",
      "strike": 22450,
      "option_type": "CE",
      "side": "LONG",
      "entry_price": 94.9,
      "pnl": 0.0,
      "signal_reason": "+5.23% spike in 60s",
      "created_at": "2026-07-10T09:31:04Z",
      "notification_sent": true
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

#### `GET /trades/{trade_id}`
Single trade by UUID. Returns 404 if not found.

---

### Replay

#### `POST /debug/replay`
Replay a newline-delimited JSON tick file through the exact same pipeline as the live WebSocket.

**Query params:**
- `reset_window` (bool, default false) — clear Redis price window before replay
- `reset_metrics` (bool, default false) — clear latency samples before replay

**Request body:** `Content-Type: application/x-ndjson`
```
{"security_id": "13", "ltp": 22450.5, "ts": "2026-07-10T09:31:04.221Z"}
{"security_id": "13", "ltp": 22451.0, "ts": "2026-07-10T09:31:05.221Z"}
```

**Response:**
```json
{"processed": 120, "signals": 1, "errors": 0, "latency_stats": {"p99_ms": 2.1, "sla_met": true}}
```

---

### Metrics

#### `GET /metrics/latency`
Tick-to-signal latency percentiles (excludes DB write and Celery enqueue).

```json
{
  "p50_ms": 0.412, "p95_ms": 0.891, "p99_ms": 2.134,
  "max_ms": 4.201, "count": 120, "sla_met": true,
  "sla_target_ms": 50.0, "measured_at": "2026-07-10T09:35:00Z"
}
```

#### `POST /metrics/reset`
Clear all latency samples.

#### `GET /reconciliation/status`
```json
{"pending_reconciliation": 0, "permanently_failed": 0, "measured_at": "..."}
```

---

### AI Query

#### `POST /ask`

**Request:**
```json
{"question": "Which strike performed best today?"}
```

**Response:**
```json
{
  "answer": "The best performing strike was NIFTY 22450 CE with total P&L of ₹847.20 across 9 trades.",
  "model": "llama-3.3-70b-versatile",
  "turns": 2
}
```

**Example questions:** "What was the last trade?" · "Show today's losing trades." · "Which strike performed best?" · "Compare CE vs PE profitability."

**MCP Tools:**
| Tool | Description |
|---|---|
| `get_last_trade` | Most recent trade record |
| `get_open_positions` | Recent simulated open positions |
| `get_pnl_summary` | Total / avg / max / min P&L |
| `get_spike_events` | Recent spike-triggered events |
| `get_best_strike_accuracy` | Strike with highest total P&L |
| `generate_trade_chart` | Text chart of last 20 trades with win rate |

---

## Design Decisions

### Redis Sorted Sets for the Rolling Window

- **O(log N) append** via `ZADD` with ms timestamp as score
- **O(log N) range delete** via `ZREMRANGEBYSCORE` to evict ticks older than 60s
- **O(1) oldest-entry lookup** via `ZRANGEBYSCORE(cutoff, +inf, limit=1)`
- Atomic pipeline: `ZADD + ZREMRANGEBYSCORE + EXPIRE` in a single round-trip

### ATM Strike Rounding (22425 → 22450)

Decision: **round-half-up** using `floor(spot/50 + 0.5) * 50`. Python's `round()` uses banker's rounding (22425 → 22400) which produces surprising results in single-trade scenarios. Financial conventions universally use round-half-up.

### Celery Broker: Redis

Redis was chosen because it is already in the stack (price window + cooldown). **Durability tradeoff:** AOF persistence is off in the default config. The Celery Beat reconciliation task (every 60s) recovers any dropped notifications, making this acceptable for trading alerts.

### Provider-Agnostic LLM Layer

`BaseLLMProvider` abstract class with three implementations: Groq, OpenAI, Ollama. Switch with one env var (`LLM_PROVIDER`). Adding a new provider requires only a new file — zero changes to service or router.

---

## Failure Semantics

### Q1: Postgres commits, Celery broker is unreachable

`_enqueue_notification()` catches the broker error — DB commit is preserved. Beat reconciliation re-enqueues within 60 seconds of broker recovery.

### Q2: Worker sends webhook, crashes before ACKing

`task_acks_late=True` + `task_reject_on_worker_lost=True` requeues the task. On redelivery, Redis `SETNX` finds the idempotency key (set before the HTTP call) → returns False → task exits with `skipped`. User sees exactly one message.

### Q3: 4-worker pool, 200 spikes in 10 seconds

`ingest_tick()` is fully async and dispatches signal handling via `asyncio.create_task()` — tick processing is never blocked. The 60-second per-security cooldown (Redis SETNX) limits signals to one per security per minute, naturally throttling the queue.

---

## Running the Benchmark

> Activate the venv first: `source venv/bin/activate`

```bash
# Basic run — resets window so the spike always fires
python scripts/benchmark.py

# Keep existing window state (spike won't fire if cooldown is active)
python scripts/benchmark.py --no-reset-window

# Custom file and server URL
python scripts/benchmark.py \
  --file tests/fixtures/sample_replay.ndjson \
  --url http://localhost:8000

# Generate a larger fixture (more ticks = more stable p99)
python scripts/generate_replay.py \
  --ticks 500 \
  --base-price 22000 \
  --spike-pct 5.5 \
  --spike-at 65 \
  --output tests/fixtures/large_replay.ndjson

python scripts/benchmark.py --file tests/fixtures/large_replay.ndjson

# Machine-readable JSON output (exit 0 = SLA met, exit 1 = SLA breached)
python scripts/benchmark.py --json

# Docker (production)
docker compose exec app python scripts/benchmark.py
```

**All benchmark flags:**
| Flag | Default | Description |
|---|---|---|
| `--file` | `tests/fixtures/sample_replay.ndjson` | NDJSON replay file |
| `--url` | `http://localhost:8000` | Server base URL |
| `--reset-window` | enabled | Clear Redis price window before run (spike fires) |
| `--no-reset-window` | — | Keep existing window (spike may be suppressed by cooldown) |
| `--json` | — | Output raw JSON instead of formatted report |

**generate_replay.py flags:**
| Flag | Default | Description |
|---|---|---|
| `--ticks` | 120 | Number of ticks to generate |
| `--base-price` | 22000 | Starting LTP price |
| `--spike-pct` | 5.5 | Spike magnitude (%) above base price |
| `--spike-at` | 65 | Tick index where spike fires (must be > 60) |
| `--output` | `tests/fixtures/sample_replay.ndjson` | Output file path |
| `--security-id` | 13 | Security ID in each tick |

**Expected output:**
```
=======================================================
  INSTANT STRIKE — LATENCY BENCHMARK REPORT
=======================================================
  Ticks sent       : 120
  Ticks processed  : 120
  Signals detected : 1
  Errors           : 0

  Server-side tick-to-signal latency
    p50  :    0.412 ms
    p95  :    0.891 ms
    p99  :    2.134 ms   ← SLA target: <50ms
    max  :    4.201 ms
    n    :      120

  SLA (p99 < 50ms) : ✓ PASS
=======================================================
```
