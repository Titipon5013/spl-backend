-- Run against existing PostgreSQL DB after pulling Feature 4 (admin LINE) changes
-- Backs UC-10 (push alerts) and UC-11 (admin conversational queries)

CREATE TABLE IF NOT EXISTS admin_alert_subscriptions (
    id            SERIAL PRIMARY KEY,
    line_user_id  VARCHAR(64)  NOT NULL UNIQUE,
    admin_id      INTEGER      REFERENCES admins(id),
    alert_types   VARCHAR(200) NOT NULL DEFAULT 'stuck_slot,pipeline_inactive,device_offline',
    muted         BOOLEAN      NOT NULL DEFAULT FALSE,
    linked_at     TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_admin_alert_subscriptions_line_user_id
    ON admin_alert_subscriptions (line_user_id);

CREATE TABLE IF NOT EXISTS admin_alert_deliveries (
    id            SERIAL PRIMARY KEY,
    anomaly_id    INTEGER      NOT NULL REFERENCES system_anomalies(id),
    line_user_id  VARCHAR(64)  NOT NULL,
    sent_at       TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE (anomaly_id, line_user_id)
);

CREATE INDEX IF NOT EXISTS ix_admin_alert_deliveries_anomaly_id
    ON admin_alert_deliveries (anomaly_id);
CREATE INDEX IF NOT EXISTS ix_admin_alert_deliveries_line_user_id
    ON admin_alert_deliveries (line_user_id);
