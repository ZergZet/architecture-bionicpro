CREATE DATABASE IF NOT EXISTS mart;

-- Сырые события телеметрии
CREATE TABLE IF NOT EXISTS mart.telemetry_events
(
    serial_number    String,
    event_type       String,
    event_time       DateTime,
    response_time_ms Float64,
    battery_level    Float64,
    signal_quality   Float64,
    error_code       String,
    ingested_at      DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (serial_number, event_time);

-- Витрина «клиент + агрегированная телеметрия»
-- Схема оптимизирована под быстрый доступ к данным клиента:
--   * ORDER BY (client_id, serial_number) — первичный ключ, ускоряет выборки по клиенту
--   * все ключевые метрики телеметрии сгруппированы по клиенту и протезу
CREATE TABLE IF NOT EXISTS mart.client_telemetry_analytics
(
    client_id            UInt32,
    full_name            String,
    email                String,
    username             String,
    prosthesis_type      String,
    prosthesis_model     String,
    serial_number        String,
    order_number         String,
    order_price          Decimal(12,2),
    install_date         Date,

    total_events         UInt32,
    avg_response_time    Float64,
    avg_battery_level    Float64,
    avg_signal_quality   Float64,
    error_events         UInt32,
    last_event_time      DateTime,
    updated_at           DateTime DEFAULT now()
)
ENGINE = MergeTree
ORDER BY (client_id, serial_number);

-- Дополнительный индекс для быстрого поиска по модели протеза
ALTER TABLE mart.client_telemetry_analytics
    ADD INDEX IF NOT EXISTS idx_model prosthesis_model TYPE set(0) GRANULARITY 1;