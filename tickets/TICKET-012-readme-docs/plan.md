# Plan: TICKET-012 — README & API Documentation

## Branch
```bash
git checkout -b feature/TICKET-012-readme-docs
```

## Implementation Steps

### Step 1 — Gather real data before writing
Before writing README, run the full system and collect:
```bash
# 1. Run benchmark to get real latency numbers
python scripts/benchmark.py --ticks 2000 > /tmp/latency_results.txt

# 2. Run a replay that generates trades
curl -X POST http://localhost:8000/debug/replay?reset_window=true \
  --data-binary @tests/sample_replay.ndjson | python -m json.tool

# 3. Capture docker compose logs to verify Celery tasks
docker compose logs celery-worker 2>&1 | grep -E "notification|reconcile" | head -20
```

### Step 2 — README Structure

```markdown
# Instant Strike Execution Engine

Low-latency NIFTY options execution engine. Detects ±5% price spikes in 60-second 
windows and simulates option trades with async persistence, Celery notifications, 
and an AI-powered query layer.

## Quick Start
\`\`\`bash
cp .env.example .env
# Fill in DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN, ANTHROPIC_API_KEY
docker compose up --build
curl http://localhost:8000/health
\`\`\`

## Architecture

[Mermaid diagram — copy from TICKET-012 ticket.md]

## Architecture Decisions

### Redis Structure: Sorted Sets
[One paragraph: why ZSET over Streams/Lists, tradeoffs]

### Broker Choice: Redis
[One paragraph: Redis vs RabbitMQ, durability tradeoff accepted]

### Index Choice: created_at + notification_sent
[One paragraph: which queries these serve, why not more indexes]

### ATM Rounding: Round-Half-Up at 22425
[One paragraph: Python banker's rounding vs financial convention, decision]

## Celery Failure Semantics

### Q1: Postgres commits, broker unreachable
[Answer from TICKET-008]

### Q2: Worker crashes after send, before ACK
[Answer from TICKET-008]

### Q3: 200 spikes, 4-worker pool
[Answer from TICKET-008]

## Latency Numbers

### Methodology
Measurement scope: from tick entry into \`ingest_tick()\` to signal decision return.
NOT included: Postgres write, Celery enqueue.
Code: \`app/metrics/latency.py\`, \`app/features/ingestion/pipeline.py\` (time.perf_counter wraps Redis ops + detect).
Reproduction: \`python scripts/benchmark.py --ticks 2000\`

### Results (local Docker, same host)
| Metric | Value |
|--------|-------|
| p50    | Xms   |
| p95    | Xms   |
| p99    | Xms   |
| max    | Xms   |
| SLA    | PASS/FAIL |

[Fill with actual numbers from benchmark]

## What I Cut & Why
[Honest list of descoped items with priority reasoning]

## Questions I Asked
[Ambiguities identified, decisions made]

## One Thing I Got Wrong
[Real learning from implementation]

## API Reference
See \`http://localhost:8000/docs\` for interactive API documentation.
```

### Step 3 — Complete `.env.example`
Verify every `settings.*` reference in the codebase is documented:
```bash
grep -r "settings\." app/ | grep -oP "settings\.\w+" | sort -u
```
Then document each in `.env.example`.

### Step 4 — FastAPI Route Docstrings
Ensure every route has a docstring (FastAPI uses these for OpenAPI):
```python
@router.post("/debug/replay")
async def replay(...):
    """
    Replay a newline-delimited JSON tick file through the live pipeline.
    
    Each line must be: {"security_id": "13", "ltp": 22450.5, "ts": "2026-07-10T09:31:04.221Z"}
    
    This endpoint uses the same code path as the live WebSocket consumer.
    Query params:
    - reset_window: flush Redis price window before replay (default: false)
    - reset_metrics: clear latency samples before replay (default: false)
    """
```

### Step 5 — Mermaid Diagram Validation
Test the Mermaid diagram renders correctly by pasting it into:
- https://mermaid.live (or preview in VS Code with Mermaid plugin)
- GitHub README preview

### Step 6 — Final Checklist Before Commit
```bash
# All services start
docker compose up --build -d && sleep 10
curl http://localhost:8000/health

# Replay produces trades
curl -X POST "http://localhost:8000/debug/replay?reset_window=true" \
  --data-binary @tests/sample_replay.ndjson

# AI layer works
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What was the last trade?"}'

# Latency SLA
python scripts/benchmark.py --ticks 2000

# API docs render
open http://localhost:8000/docs
```

## Commit Message
```
docs: write comprehensive README with architecture decisions, failure semantics, and latency methodology
```
