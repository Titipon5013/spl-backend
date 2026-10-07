-- Apply once to the existing PostgreSQL database before deploying the gate
-- event subscriber. Gate event counts are derived from this durable log.
CREATE TABLE IF NOT EXISTS gate_events (
    id SERIAL PRIMARY KEY,
    event VARCHAR(10) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    gate_id VARCHAR(100) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    vehicle_class VARCHAR(50),
    confidence DOUBLE PRECISION,
    camera INTEGER,
    open_duration_seconds DOUBLE PRECISION,
    open_count_today INTEGER,
    close_count_today INTEGER,
    CONSTRAINT uq_gate_events_event_id UNIQUE (event_id)
);

CREATE INDEX IF NOT EXISTS ix_gate_events_event ON gate_events (event);
CREATE INDEX IF NOT EXISTS ix_gate_events_gate_id ON gate_events (gate_id);
CREATE INDEX IF NOT EXISTS ix_gate_events_timestamp ON gate_events (timestamp);
