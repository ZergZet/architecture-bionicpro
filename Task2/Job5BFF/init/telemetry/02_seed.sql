-- По 20 событий на каждый из 50 серийных номеров (SN-000001 … SN-000050)
INSERT INTO telemetry (
    serial_number, event_type, event_time,
    response_time_ms, battery_level, signal_quality, error_code
)
SELECT
    'SN-' || lpad(c::text, 6, '0'),

    (ARRAY['activation','movement','charging','calibration',
           'error','shutdown','firmware_update'])[1 + (t % 7)],

    NOW()
      - make_interval(days => (random() * 30)::int)
      - make_interval(secs => (random() * 86400)::int),

    round((15 + random() * 285)::numeric, 2),               -- отклик, мс
    round((random() * 100)::numeric, 2),                    -- заряд, %
    round((30 + random() * 70)::numeric, 2),                -- качество, %

    CASE WHEN (t % 7) = 4
         THEN 'E' || lpad((100 + (t % 20))::text, 3, '0')
         ELSE NULL
    END
FROM generate_series(1, 50) AS c
CROSS JOIN generate_series(1, 20) AS t;