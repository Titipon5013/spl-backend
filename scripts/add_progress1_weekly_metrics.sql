-- Run against existing PostgreSQL DB after pulling the Feature 5 weekly-report changes.
-- Adds the permanent per-lot weekly summary table and lot attribution on entry records.
--
-- weekly_lot_metrics: one row per lot per calendar week (Mon 00:00 UTC -> next Mon 00:00 UTC,
-- week_end exclusive). The report scheduler upserts these rows right before sending the
-- weekly emails, so the summary survives raw-data cleanup and repeat triggers never
-- create duplicates.

ALTER TABLE entry_records ADD COLUMN IF NOT EXISTS lot_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS ix_entry_records_lot_id ON entry_records (lot_id);

CREATE TABLE IF NOT EXISTS weekly_lot_metrics (
    id                      SERIAL PRIMARY KEY,
    lot_id                  VARCHAR(50)      NOT NULL,
    week_start              TIMESTAMP        NOT NULL,
    week_end                TIMESTAMP        NOT NULL,
    utilization_percentage  DOUBLE PRECISION NOT NULL DEFAULT 0,
    peak_occupancy          INTEGER          NOT NULL DEFAULT 0,
    vehicle_count           INTEGER          NOT NULL DEFAULT 0,
    avg_dwell_time_minutes  DOUBLE PRECISION NOT NULL DEFAULT 0,
    generated_at            TIMESTAMP        NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_weekly_lot_metric UNIQUE (lot_id, week_start)
);

CREATE INDEX IF NOT EXISTS ix_weekly_lot_metrics_lot_id     ON weekly_lot_metrics (lot_id);
CREATE INDEX IF NOT EXISTS ix_weekly_lot_metrics_week_start ON weekly_lot_metrics (week_start);
