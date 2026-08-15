# Feature 4 — Admin LINE Bot and Notifications

Progress II Feature 4 (Option B). Administrators link a LINE account, ask
questions that are answered via Feature 2 MCP tools, and receive push alerts
when `AnomalyService` opens a new anomaly.

## Endpoints

| Path | Purpose |
|---|---|
| `POST /webhook/line/admin` | Admin LINE webhook (separate channel from Feature 6) |

## Setup

1. Create the subscription tables:

   ```bash
   psql "$DATABASE_URL" -f scripts/add_progress2_admin_alert_subscription.sql
   ```

2. Add Feature 4 variables to `.env` (see `.env.example`):

   | Variable | Purpose |
   |---|---|
   | `ADMIN_LINE_CHANNEL_SECRET` | LINE channel secret for the admin OA |
   | `ADMIN_LINE_ACCESS_TOKEN` | LINE channel access token (reply + push) |
   | `ADMIN_LINE_LINK_SECRET` | Shared secret for `/link <secret>` |
   | `MCP_LINE_BOT_TOKEN` | Bearer token the bot uses at `/mcp` |
   | `MCP_API_TOKENS` | Must include `MCP_LINE_BOT_TOKEN` |
   | `MCP_INTERNAL_URL` | Default `http://127.0.0.1:8000/mcp/` |
   | `CLOUD_API_KEY` / `AGENT_ENDPOINT` | LLM used for tool orchestration |

3. Point the admin LINE Official Account webhook to
   `https://<host>/webhook/line/admin`.

**Windows teammates:** step-by-step local setup (venv, Postgres, ngrok, MCP curl,
LINE checklist) is in [windows-local-test-guide.md](windows-local-test-guide.md).

## Admin commands

| Command | Effect |
|---|---|
| `/link <secret>` | Upsert `AdminAlertSubscription` for this LINE user |
| `/mute` | Stop push alerts (chat still works) |
| `/unmute` | Resume push alerts |
| `/settings` | Show mute status and alert types |

Unlinked users cannot query MCP; they receive link instructions instead.

## Alert policy (current)

While campus services may be paused / noisy, LINE **pushes only `device_offline`**
by default (board / cameras — same idea as dashboard System Health).

- Per-spot `stuck_slot` alerts are **not** pushed by default (too frequent).
- Override with `ADMIN_PUSH_ALERT_TYPES` in `.env`, e.g.
  `device_offline,pipeline_inactive`.
- Old subscriptions that still list all anomaly types are treated as the new default.

Chat replies are worded like a colleague on LINE (short, natural), not raw JSON dumps.

## Data flow

1. Linked admin texts a question → `AdminChatbotService` → `McpClient.call_tool`
   → Feature 2 tools over HTTP (or `MCP_INTERNAL_MODE=inprocess` in tests).
2. Scheduler runs `detect_anomalies` → `AdminNotificationService.dispatch_new_anomaly_alerts`
   → LINE push to unmuted subscribers → `admin_alert_deliveries` dedupes.
