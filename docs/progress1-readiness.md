# ParkPilot Progress I Readiness

Last reviewed: 2026-06-19

This note records what is accepted for Progress I, what still needs formal evidence, and what should move forward as an integration follow-up.

## Progress I Scope

Progress I covers:

- F1 Real-Time Parking Monitoring and Analytics Foundation
- F3 Administrator Analytics Dashboard
- F5 Access Management and Automated Reporting

Progress II covers MCP server work, full LINE chatbot workflows, commuter-facing ETA, and predictive routing.

## Current Verification Evidence

Backend automated verification:

```bash
pytest -q
```

Latest observed result:

```text
91 passed
```

Frontend automated verification:

```bash
npm test
```

Latest observed result:

```text
6 test files passed, 8 tests passed
```

Frontend browser-level verification on Firefox:

```bash
npm run test:e2e
```

Latest observed result:

```text
4 Playwright Firefox tests passed
```

Frontend static verification:

```bash
npm run lint
```

Latest observed result:

```text
eslint completed successfully
```

Frontend production build:

```bash
npm run build
```

Latest observed result:

```text
vite build completed successfully
```

Known non-blocking warning: the production JavaScript bundle is larger than Vite's default 500 kB warning threshold.

## Closed Since Last Review

1. Formal F3 dashboard verification is now automated in the frontend repository with component-level and Firefox browser-level coverage.

   Covered evidence:

   - `ProtectedRoute.test.tsx` and `e2e/progress1.spec.ts`: protected dashboard route redirects without a token.
   - `AnalyticsPage.test.tsx` and `e2e/progress1.spec.ts`: dashboard capacity, KPI cards, node status, heatmap spots, and lot-filtered API requests render from mocked backend APIs.
   - `SpatialHeatmap.test.tsx` and `e2e/progress1.spec.ts`: low, moderate, and high heatmap thresholds render in the dashboard flow.
   - `SystemHealthPage.test.tsx` and `e2e/progress1.spec.ts`: board/camera status, degraded camera count, and incident warning render from health API data.
   - `WeeklyReportPage.test.tsx` and `e2e/progress1.spec.ts`: weekly trend insight, KPI summary, and uptime render from analytics APIs.
   - `ExportReportTools.test.tsx` and `e2e/progress1.spec.ts`: CSV/PDF export buttons request downloadable analytics files and produce browser downloads.

2. Formal F5 weekly report verification is now automated in the backend repository.

   Covered evidence:

   - `test_weekly_scheduler_dispatches_reports_to_approved_admins`: weekly report dispatch generates CSV/PDF exports and sends them to approved administrators.
   - `test_start_report_scheduler_registers_weekly_cron_job`: scheduler registers the configured weekly cron job.
   - `test_trigger_weekly_report`: manual endpoint `POST /api/reports/trigger` calls report dispatch.

## Acceptance Position

For Progress I, treat the backend and frontend analytics contract as accepted when camera events and heartbeat payloads flow through the real FastAPI ingestion endpoints and the dashboard can read the resulting analytics APIs.

The backend supports both direct edge posting and backend-pulled edge JSON ingestion. The real Orange Pi / YOLO producer still needs to expose JSON or publish MQTT from the edge machine. Do not claim that this repository contains the YOLO/OpenCV model pipeline. Claim that the backend ingestion API, edge JSON pull adapter, persistence model, analytics queries, and dashboard consumption are implemented.

## Must Close Before Submission

1. Confirm production live camera routing.

   The frontend loads HLS streams from same-origin paths:

   - `/parking/index.m3u8`
   - `/parking2/index.m3u8`
   - `/license/index.m3u8`
   - `/license1/index.m3u8`

   Before replacing production frontend files, confirm that the CAMT server already proxies these paths to the camera/HLS source.

2. Make database setup reproducible.

   Progress I admin access columns are currently documented in `scripts/add_progress1_admin_columns.sql`. Before deployment or handoff, either convert the SQL into an Alembic migration or include the SQL script explicitly in the deployment steps.

3. Capture real or adapter-based edge ingestion evidence.

   Preferred real-network check:

   ```bash
   curl -X POST http://127.0.0.1:8000/api/analytics/edge/sync
   ```

   If the edge machine is unavailable, use the simulator as a temporary local fallback:

   ```bash
   python scripts/simulate_camera_events.py --api-url http://127.0.0.1:8000 --count 5 --interval 5
   ```

   Then verify:

   - `GET /api/analytics/current?lot_id=CAMT_01`
   - `GET /api/analytics/current?lot_id=CAMT_02`
   - `GET /api/analytics/heatmap?lot_id=CAMT_01`
   - `GET /api/analytics/health`

## Integration Follow-Up

Real edge integration is ready on the backend side when the Orange Pi / YOLO service exposes structured JSON matching `CameraEventPayload`, MQTT-style `ParkingPayload`, and `DeviceHeartbeatPayload`.

Preferred flow:

```text
Camera stream
-> Orange Pi / YOLO detector
-> structured edge JSON or MQTT payload
-> backend edge poller or direct POST /api/analytics/camera/events
-> PostgreSQL snapshots and event logs
-> dashboard analytics APIs
```

Open integration questions:

- Where is the edge service repository or deployment package?
- Do `/infer/parking1` and `/infer/parking2` return JSON, images only, or both?
- What are the canonical spot IDs for Parking Area 1 and Parking Area 2?
- Should License Check 1 and License Check 2 create `EntryRecord` rows in Progress I, or are they live-monitoring-only?
