# TICKET-010: MCP Server & AI Trade Intelligence Layer

**Branch:** `feature/TICKET-010-mcp-ai-layer`  
**Priority:** P2 — Can be parallelized with other P1 tickets  
**Estimate:** ~3h

## Summary
Build the AI query layer: an MCP-compatible server exposing 6 trade intelligence tools, and a `POST /ask` natural language endpoint powered by an LLM. The LLM uses MCP tools as function calls to answer trade queries.

## MCP Server

**Library:** `fastmcp` (FastMCP Python library)  
**LLM Integration:** Claude API (Anthropic) via `anthropic` SDK with tool use

### 6 MCP Tools

#### 1. `get_last_trade()`
Returns the most recently created trade.
```python
@mcp.tool()
async def get_last_trade() -> dict:
    """Get the most recently executed trade."""
    trade = await db.execute(
        select(Trade).order_by(Trade.created_at.desc()).limit(1)
    )
    return trade_to_dict(trade.scalar_one_or_none())
```

#### 2. `get_open_positions()`
Returns trades with `pnl=0.0` (no exit recorded yet — proxy for "open").
```python
@mcp.tool()
async def get_open_positions() -> list[dict]:
    """Get all currently open positions (no exit price recorded)."""
```

#### 3. `get_pnl_summary()`
Aggregate PnL grouped by option_type and side.
```python
@mcp.tool()
async def get_pnl_summary() -> dict:
    """Get PnL summary: total, by CE/PE, by LONG/SHORT, win rate."""
```

#### 4. `get_spike_events(limit: int = 20)`
Returns recent spike events from trades table (signal_reason field).
```python
@mcp.tool()
async def get_spike_events(limit: int = 20) -> list[dict]:
    """Get recent spike detection events with signal details."""
```

#### 5. `get_best_strike_accuracy()`
Which strike price had the best average PnL?
```python
@mcp.tool()
async def get_best_strike_accuracy() -> list[dict]:
    """Rank strikes by average PnL to find most accurate ATM selection."""
    # SELECT strike, AVG(pnl), COUNT(*) FROM trades GROUP BY strike ORDER BY AVG(pnl) DESC
```

#### 6. `generate_trade_chart()`
Returns a base64-encoded PNG or ASCII chart of PnL over time.
```python
@mcp.tool()
async def generate_trade_chart() -> dict:
    """Generate a PnL timeline chart. Returns base64 PNG."""
    # Use matplotlib to render, return as base64
```

## Natural Language Endpoint

### `POST /ask`
```python
@router.post("/ask")
async def ask_question(body: AskRequest):
    """
    Natural language trade query using Claude with MCP tools.
    Example: {"question": "What was the last trade?"}
    """
```

### LLM Integration Pattern (Claude API with Tool Use)
```python
async def answer_question(question: str) -> str:
    tools = [
        get_last_trade_tool_schema,
        get_open_positions_tool_schema,
        get_pnl_summary_tool_schema,
        get_spike_events_tool_schema,
        get_best_strike_accuracy_tool_schema,
        generate_trade_chart_tool_schema,
    ]
    
    messages = [{"role": "user", "content": question}]
    
    # Agentic loop: LLM calls tools until it has enough info
    while True:
        response = await anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",  # fast + cheap for this use case
            max_tokens=1024,
            tools=tools,
            messages=messages,
        )
        
        if response.stop_reason == "end_turn":
            return extract_text(response)
        
        # Execute tool calls
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = await execute_mcp_tool(block.name, block.input)
                tool_results.append({"tool_use_id": block.id, "content": json.dumps(result)})
        
        messages.extend([
            {"role": "assistant", "content": response.content},
            {"role": "user", "content": tool_results},
        ])
```

### Example Queries
| Query | Expected Tool Call |
|---|---|
| "What was the last trade?" | `get_last_trade()` |
| "Show today's losing trades." | `get_pnl_summary()` + filter |
| "Which strike performed best?" | `get_best_strike_accuracy()` |
| "Compare CE vs PE profitability." | `get_pnl_summary()` |

## Files to Create
- `app/features/ai/mcp_server.py` — FastMCP server with 6 tools
- `app/features/ai/tools.py` — Tool implementations (DB queries)
- `app/features/ai/service.py` — LLM client + agentic loop
- `app/features/ai/router.py` — `POST /ask` route
- `app/external/anthropic/client.py` — Claude API client

## Acceptance Criteria
- [ ] All 6 MCP tools return correct data from Postgres
- [ ] `POST /ask` with "What was the last trade?" returns a coherent answer
- [ ] `POST /ask` with "Compare CE vs PE profitability." calls `get_pnl_summary()`
- [ ] `generate_trade_chart()` returns a valid base64-encoded image
- [ ] LLM correctly routes questions to the right tools (agentic tool use loop)
- [ ] Graceful response when no trades exist yet ("No trades recorded yet.")
- [ ] API key for LLM loaded from `.env` (ANTHROPIC_API_KEY)

## Dependencies
- TICKET-001 (FastAPI, project structure)
- TICKET-002 (Trade model, DB session)

## Notes
- Use `claude-haiku-4-5-20251001` for fast, cost-efficient responses
- If ANTHROPIC_API_KEY not set, fall back to a deterministic response ("AI layer not configured")
- MCP server can also be mounted as an SSE endpoint for external MCP clients
