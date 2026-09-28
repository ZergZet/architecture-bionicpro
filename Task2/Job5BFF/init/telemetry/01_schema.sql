CREATE TABLE IF NOT EXISTS telemetry (
    id                BIGSERIAL PRIMARY KEY,
    serial_number     VARCHAR(50) NOT NULL,
    event_type        VARCHAR(50) NOT NULL,
    event_time        TIMESTAMPTZ NOT NULL,
    response_time_ms  NUMERIC(8,2),
    battery_level     NUMERIC(5,2),
    signal_quality    NUMERIC(5,2),
    error_code        VARCHAR(20)
);

CREATE INDEX IF NOT EXISTS idx_telemetry_serial_time
    ON telemetry(serial_number, event_time DESC);