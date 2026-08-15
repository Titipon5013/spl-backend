# Windows Local Test Guide — Feature 2 + Feature 4 (+ Feature 6)

For teammates on **Windows** who want to pull `dev` and verify MCP + admin LINE locally.

**Time:** ~30–45 min first setup, ~10 min later runs.

---

## 0. What you are testing

| Feature | What to prove |
|---|---|
| **F2 MCP** | `POST /mcp/` accepts a bearer token and returns tools / occupancy |
| **F4 Admin LINE** | `/link`, ask a question (goes through MCP), `/mute`, anomaly push |
| **F6 User LINE** | Still on `/webhook/line/user` (separate channel) — optional |

LINE webhooks need a **public HTTPS URL**. On Windows use **ngrok** (or Cloudflare Tunnel).

---

## 1. Install tools (one-time)

1. **Git** — https://git-scm.com/download/win  
2. **Python 3.11+** — https://www.python.org/downloads/  
   - Check **“Add python.exe to PATH”** during install  
3. **PostgreSQL 15+** (recommended) — or Docker Desktop + a Postgres container  
4. **ngrok** — https://ngrok.com/download (for LINE only)  
5. Optional: **VS Code** / Cursor, **Postman**

Open **PowerShell** and check:

```powershell
python --version
git --version
```

---

## 2. Get the code

```powershell
cd $HOME\Documents
git clone <REPO_URL> spl-backend
cd spl-backend
git checkout dev
git pull origin dev
```

If you already have the repo:

```powershell
cd path\to\spl-backend
git checkout dev
git pull origin dev
```

---

## 3. Python venv + deps

```powershell
cd path\to\spl-backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks the activate script:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```

---

## 4. Configure `.env`

```powershell
Copy-Item .env.example .env
notepad .env
```

### Minimum for local API + MCP (no LINE yet)

```env
DATABASE_URL=postgresql+psycopg2://postgres:YOUR_PASSWORD@127.0.0.1:5432/smartparkinglot
SECRET_KEY=dev-secret-change-me
SQL_ECHO=false

MCP_API_TOKENS=dev-mcp-token-for-friends
MCP_HTTP_ENABLED=true
MCP_LINE_BOT_TOKEN=dev-mcp-token-for-friends
MCP_INTERNAL_URL=http://127.0.0.1:8000/mcp/
MCP_INTERNAL_MODE=http
MCP_ALLOWED_HOSTS=localhost,localhost:8000,127.0.0.1,127.0.0.1:8000

ANOMALY_SCAN_INTERVAL_MINUTES=5
ANOMALY_STUCK_SLOT_HOURS=12
ANOMALY_PIPELINE_INACTIVE_MINUTES=15
ANOMALY_DEVICE_OFFLINE_SECONDS=300

EMAIL_DISABLED=true
```

`MCP_LINE_BOT_TOKEN` **must** be one of the values in `MCP_API_TOKENS`.

### Extra for Feature 4 (admin LINE)

```env
ADMIN_LINE_CHANNEL_SECRET=from_line_developers_console
ADMIN_LINE_ACCESS_TOKEN=from_line_developers_console
ADMIN_LINE_LINK_SECRET=parkpilot-link-test
CLOUD_API_KEY=your_openrouter_or_llm_key
AGENT_ENDPOINT=https://openrouter.ai/api/v1/chat/completions
```

### Extra for Feature 6 (user LINE) — optional

```env
USER_LINE_CHANNEL_SECRET=...
# plus whatever the user webhook already expects (see existing F6 setup)
```

---

## 5. Create DB tables (Postgres)

In **SQL Shell (psql)** or pgAdmin, create DB if needed:

```sql
CREATE DATABASE smartparkinglot;
```

Then from PowerShell (adjust user/db):

```powershell
# If psql is on PATH:
$env:PGPASSWORD="YOUR_PASSWORD"
psql -U postgres -d smartparkinglot -f scripts\add_progress2_anomaly_table.sql
psql -U postgres -d smartparkinglot -f scripts\add_progress2_admin_alert_subscription.sql
```

If the app already auto-creates tables via SQLAlchemy elsewhere, still run these two scripts — they match Progress II / F4.

> **Note:** This project historically uses raw SQL scripts for Progress II tables (not only Alembic). Prefer the scripts above for F2/F4.

---

## 6. Start the API

Keep venv active:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Open: http://127.0.0.1:8000/docs

---

## 7. Seed some parking data (needed for MCP answers)

In a **second** PowerShell (venv on):

```powershell
cd path\to\spl-backend
.\.venv\Scripts\Activate.ps1
python scripts\simulate_camera_events.py --api-url http://127.0.0.1:8000 --count 5 --interval 2
```

If that script needs different auth/headers in your env, check `scripts/simulate_camera_events.py` help:

```powershell
python scripts\simulate_camera_events.py --help
```

---

## 8. Test Feature 2 (MCP) without LINE

PowerShell:

```powershell
$token = "dev-mcp-token-for-friends"
$headers = @{
  Authorization = "Bearer $token"
  "Content-Type" = "application/json"
  Accept = "application/json, text/event-stream"
}

# 1) initialize
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/mcp/" -Headers $headers -Body (@{
  jsonrpc = "2.0"; id = 1; method = "initialize"
  params = @{
    protocolVersion = "2025-06-18"
    capabilities = @{}
    clientInfo = @{ name = "windows-friend"; version = "1.0" }
  }
} | ConvertTo-Json -Depth 6)

# 2) initialized notification
Invoke-WebRequest -Method Post -Uri "http://127.0.0.1:8000/mcp/" -Headers $headers -Body (@{
  jsonrpc = "2.0"; method = "notifications/initialized"
} | ConvertTo-Json) | Out-Null

# 3) list tools — expect 8 tools
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/mcp/" -Headers $headers -Body (@{
  jsonrpc = "2.0"; id = 2; method = "tools/list"
} | ConvertTo-Json)
```

**Pass if:** unauthorized without token; with token you see tools including `get_live_occupancy`, `get_system_anomalies`, etc.

Wrong token must return **401**.

---

## 9. Test Feature 4 with LINE (Windows + ngrok)

### 9.1 Expose localhost

```powershell
ngrok http 8000
```

Copy the `https://....ngrok-free.app` URL.

### 9.2 LINE Developers Console (Admin OA)

1. Open the **admin** LINE Official Account channel (separate from the user/commuter bot).  
2. Messaging API → Webhook URL:

   `https://YOUR_NGROK_HOST/webhook/line/admin`

3. Enable webhook, verify.  
4. Put **Channel secret** / **Channel access token** into `.env`, restart uvicorn.

### 9.3 Chat checklist (~5 min)

In LINE, message the **admin** bot:

1. Ask anything **before** linking → should tell you to `/link`.  
2. `/link parkpilot-link-test` (use your `ADMIN_LINE_LINK_SECRET`) → “Linked”.  
3. Ask: `สถานะลานจอด CAMT_01` or `how full is CAMT_01?` → real occupancy reply (needs seeded data + `CLOUD_API_KEY`).  
4. `/settings` → push active.  
5. `/mute` → then force an anomaly (below) → **no** push.  
6. `/unmute` → force anomaly again → **get** push once.  
7. Same anomaly again → **no duplicate** push (delivery dedupe).

### 9.4 Force an anomaly locally

Easiest paths:

- Stop the camera simulator and wait past `ANOMALY_PIPELINE_INACTIVE_MINUTES` (default 15), **or**
- Temporarily set in `.env`:

  ```env
  ANOMALY_PIPELINE_INACTIVE_MINUTES=1
  ANOMALY_SCAN_INTERVAL_MINUTES=1
  ```

  Restart uvicorn, seed one event, wait >1 minute with no new events → pipeline_inactive alert.

Scheduler prints `[anomaly-detector]` / `[admin-notify]` in the uvicorn console.

---

## 10. Optional: Feature 6 smoke

Webhook path: `https://YOUR_NGROK_HOST/webhook/line/user`  
Use the **user** LINE channel secrets. Do not point the admin OA at `/line/user`.

---

## 11. Automated tests (no LINE needed)

```powershell
.\.venv\Scripts\Activate.ps1
$env:MCP_INTERNAL_MODE="inprocess"
python -m pytest test\mcp test\services\test_mcp_client.py test\services\test_admin_chatbot_service.py test\services\test_admin_notification_service.py test\controllers\test_admin_webhook_controller.py -q
```

Expect green.

---

## 12. Common Windows problems

| Symptom | Fix |
|---|---|
| `Activate.ps1` cannot run | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `psql` not found | Add Postgres `bin` to PATH, or run SQL in pgAdmin |
| MCP 401 | Same string in `MCP_API_TOKENS` and `MCP_LINE_BOT_TOKEN`; restart server |
| MCP 421 / host error | Add your Host to `MCP_ALLOWED_HOSTS` |
| LINE webhook fails | ngrok URL must be HTTPS + path `/webhook/line/admin`; signature = `ADMIN_LINE_CHANNEL_SECRET` |
| Bot says missing API key | Set `CLOUD_API_KEY` |
| Empty occupancy answers | Run `simulate_camera_events.py` first |
| Port 8000 in use | `uvicorn main:app --reload --port 8001` and update ngrok + `MCP_INTERNAL_URL` |

---

## 13. Share back with the team

When testing, send:

1. Screenshot of MCP tools/list (or pytest green)  
2. Screenshot of `/link` + occupancy reply  
3. Screenshot of anomaly LINE push (and mute not receiving)

Docs:

- [feature2-mcp-server.md](feature2-mcp-server.md)  
- [feature4-admin-line.md](feature4-admin-line.md)
