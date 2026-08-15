# Feature 2 — MCP Server for AI-Agent Integration

Progress II, Feature 2. Exposes the parking system's operational data as MCP
tools so any MCP-compatible AI agent can query it. Feature 4 (the admin LINE
bot) consumes this server rather than talking to the database directly.

## Transports

One set of tool definitions is served over two transports:

| Transport | Endpoint | Used by | Authentication |
|---|---|---|---|
| stdio | `python -m mcp_server` | Claude Desktop and other local reference clients | OS process boundary |
| streamable-http | `POST /mcp/` on the FastAPI app | Feature 4 LINE bot | `Authorization: Bearer <token>` |

## Setup

1. Install the new dependency:

   ```bash
   pip install -r requirements.txt
   ```

2. Create the anomaly table (the project does not use Alembic migrations; this
   follows the same raw-SQL pattern as Progress I):

   ```bash
   psql "$DATABASE_URL" -f scripts/add_progress2_anomaly_table.sql
   ```

3. Add the Feature 2 variables to `.env` — see `.env.example`:

   | Variable | Default | Purpose |
   |---|---|---|
   | `MCP_API_TOKENS` | *(empty)* | Comma-separated bearer tokens allowed over HTTP. Empty rejects every HTTP request. |
   | `MCP_HTTP_ENABLED` | `true` | Set `false` to run stdio-only. |
   | `MCP_ALLOWED_HOSTS` | `localhost,localhost:8000,127.0.0.1,127.0.0.1:8000` | Allowed `Host` header values (DNS rebinding protection). **Must include the CAMT server host on deploy.** |
   | `MCP_RATE_LIMIT_PER_MINUTE` | `60` | Tool invocations per client per minute (NFR-SEC-002). |
   | `ANOMALY_SCAN_INTERVAL_MINUTES` | `5` | How often the detector runs. |
   | `ANOMALY_STUCK_SLOT_HOURS` | `12` | Occupied longer than this is flagged as stuck. |
   | `ANOMALY_PIPELINE_INACTIVE_MINUTES` | `15` | No events for longer than this flags the pipeline as down. |
   | `ANOMALY_DEVICE_OFFLINE_SECONDS` | `300` | Matches the existing System Health threshold. |

   Generate a token with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

## Validating with Claude Desktop

Required by the proposal (p.34: *"Ensures validated compatibility with reference
MCP clients, such as Claude Desktop, prior to full deployment"*).

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "parkpilot": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/absolute/path/to/spl-backend",
      "env": {
        "DATABASE_URL": "postgresql+psycopg2://user:pass@localhost:5432/parkpilot"
      }
    }
  }
}
```

Restart Claude Desktop, then confirm the 8 tools appear and try a question such
as *"Which slots are free in CAMT_01 right now?"*. Screenshot this for the
Progress II test record.

## Calling it over HTTP

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer $MCP_API_TOKENS" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

An MCP client must `initialize` first; the raw call above is only for checking
that authentication and routing work.

## Tools and URS traceability

| URS | Requirement | Tool | Backed by |
|---|---|---|---|
| URS-07 | Client authentication | *(transport layer)* | `mcp_server/security.py`, `mcp_server/server.py` |
| URS-08 | Live occupancy retrieval | `get_live_occupancy` | `AnalyticsService.get_live_occupancy` |
| URS-09 | Specific slot status checking | `check_slot_status` | `AnalyticsService.check_slot_status` |
| URS-10 | Historical trends analysis | `analyze_occupancy_trends` | `AnalyticsService.get_occupancy_trends` |
| URS-11 | Vehicle dwell times retrieval | `get_dwell_time_stats` | `AnalyticsService.get_kpis` |
| URS-12 | Available slots discovery | `find_available_slots` | `AnalyticsService.find_available_slots` |
| URS-13 | System anomalies retrieval | `get_system_anomalies`, `get_system_health` | `AnomalyService.get_anomalies` |
| URS-14 | Anomaly review marking | `mark_anomaly_reviewed` | `AnomalyService.mark_anomaly_reviewed` |
| URS-15 | Schema and error enforcement | *(all tools)* | Typed signatures + `ToolError` |

## Anomaly detection

`services/anomaly_service.py` runs on the existing APScheduler in
`services/report_scheduler.py`, alongside the Progress I weekly report job.

Three detectors:

| Type | Severity | Condition |
|---|---|---|
| `stuck_slot` | warning | A slot has reported occupied for longer than `ANOMALY_STUCK_SLOT_HOURS` |
| `pipeline_inactive` | critical | No events received for a lot within `ANOMALY_PIPELINE_INACTIVE_MINUTES` |
| `device_offline` | critical for the board, warning for cameras | A device has not reported within `ANOMALY_DEVICE_OFFLINE_SECONDS` |

The detector is idempotent. An anomaly that is still ongoing is **not** inserted
again on the next scan, and it is closed automatically (`resolved_at` is set)
once the condition clears. This matters for Feature 4: the notification engine
can push an alert for every new row without ever sending duplicates.

A lot that has never reported any event is treated as "not installed yet", not
as an anomaly.

## Tests

```bash
python -m pytest test/mcp test/services/test_anomaly_service.py test/services/test_analytics_live_queries.py -q
```

33 MCP tests (tools, schemas, error contract, authentication, rate limiting) plus
18 service tests. Tools are exercised through the FastMCP dispatcher, so the
tests cover the same path an AI agent takes, including the JSON error responses.

## Notes for Feature 4

Feature 4 is implemented in this repo. The admin LINE bot consumes Feature 2
through [`services/mcp_client.py`](../services/mcp_client.py) — see
[feature4-admin-line.md](feature4-admin-line.md) for setup.

- Connect over HTTP at `/mcp/` with a bearer token from `MCP_API_TOKENS`. Do not
  import the tool functions directly — going through MCP is what the proposal
  specifies and it keeps the rate limiting in effect.
- Rate limit quota is per token, so issue the LINE bot its own token
  (`MCP_LINE_BOT_TOKEN`, also listed in `MCP_API_TOKENS`).
- After each anomaly scan, `AdminNotificationService` pushes undelivered open
  anomalies to unmuted linked admins; delivery rows prevent duplicates.
- Feature 2 is LLM-agnostic. The OpenRouter/Llama choice only affects Feature 4
  (and Feature 6) conversational orchestration.
