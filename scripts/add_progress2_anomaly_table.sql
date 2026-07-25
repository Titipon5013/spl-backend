-- Run against existing PostgreSQL DB after pulling Progress II (Feature 2) changes
-- Backs URS-13 (anomaly retrieval) and URS-14 (mark anomaly as reviewed)
CREATE TABLE IF NOT EXISTS system_anomalies (
    id            SERIAL PRIMARY KEY,
    anomaly_type  VARCHAR(30)  NOT NULL,
    severity      VARCHAR(10)  NOT NULL,
    lot_id        VARCHAR(50),
    spot_id       VARCHAR(50),
    device_id     VARCHAR(50),
    details       VARCHAR(500) NOT NULL,
    detected_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    resolved_at   TIMESTAMP,
    reviewed_by   VARCHAR(255),
    reviewed_at   TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_system_anomalies_anomaly_type ON system_anomalies (anomaly_type);
CREATE INDEX IF NOT EXISTS ix_system_anomalies_lot_id      ON system_anomalies (lot_id);
CREATE INDEX IF NOT EXISTS ix_system_anomalies_spot_id     ON system_anomalies (spot_id);
CREATE INDEX IF NOT EXISTS ix_system_anomalies_device_id   ON system_anomalies (device_id);
CREATE INDEX IF NOT EXISTS ix_system_anomalies_detected_at ON system_anomalies (detected_at);

-- The detector treats an anomaly as "still open" while resolved_at IS NULL, so this
-- partial index keeps the dedupe lookup on every detector run cheap.
CREATE INDEX IF NOT EXISTS ix_system_anomalies_open
    ON system_anomalies (anomaly_type, lot_id, spot_id, device_id)
    WHERE resolved_at IS NULL;
