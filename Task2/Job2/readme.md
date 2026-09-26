

# Запуск
```bash
chmod +x start.sh
./start.sh
```

- Заходим в Airflow: http://localhost:8080 (admin / admin)
- Включаем DAG crm_telemetry_mart 

Для тестовых целей запускается каждые 5 минут и наполняет ClickHouse-витрину.

# Структура каталогов:
```
.
├── docker-compose.yml
├── start.sh
├── README.md
├── airflow/
│   ├── Dockerfile
│   └── dags/
│       └── crm_telemetry_mart.py
└── init/
    ├── crm/
    │   ├── 01_schema.sql
    │   └── 02_seed.sql
    ├── telemetry/
    │   ├── 01_schema.sql
    │   └── 02_seed.sql
    └── clickhouse/
        └── 01_schema.sql
```

## Что разворачивается

| Сервис                | Порт (host)  | Креды                                              |
|-----------------------|--------------|----------------------------------------------------|
| PostgreSQL — CRM      | 5433         | `crm_user` / `crm_pass` / БД `crm`                 |
| PostgreSQL — Telemetry| 5434         | `telemetry_user` / `telemetry_pass` / БД `telemetry` |
| PostgreSQL — Airflow  | (внутренний) | `airflow` / `airflow` / БД `airflow`               |
| ClickHouse            | 8123 / 9000  | `default` без пароля, БД `mart`                    |
| Airflow UI            | 8080         | `admin` / `admin`                                  |

## Запуск

```bash
chmod +x start.sh
./start.sh
```

При первом запуске:
1. Разворачиваются оба PostgreSQL и создаются схемы + тестовые данные:
   - CRM: **50 клиентов**
   - Телеметрия: **20 событий на каждый протез (всего 1000 записей)**
2. ClickHouse создаёт БД `mart` и таблицы витрины.
3. Airflow прогоняет миграции и создаёт пользователя `admin`.
4. Через ~30 секунд появляется DAG `crm_telemetry_mart` и начинает выполняться
   по расписанию **раз в 5 минут**.

## Полный сброс (пересоздание БД)

```bash
docker compose down -v   # удалит все volume-ы
./start.sh
```

## Изменение расписания сбора данных

Расписание задаётся одним параметром в DAG-файле:

`airflow/dags/crm_telemetry_mart.py`, строка:

```python
SCHEDULE = "*/5 * * * *"
```

Формат — стандартный **cron**:

| Значение         | Что значит                             |
|------------------|----------------------------------------|
| `*/5 * * * *`    | каждые 5 минут (по умолчанию)          |
| `*/10 * * * *`   | каждые 10 минут                        |
| `0 * * * *`      | каждый час                             |
| `0 */2 * * *`    | каждые 2 часа                          |
| `0 6 * * *`      | каждый день в 06:00                    |
| `@hourly`        | синоним «каждый час»                   |

Для изменения расписания:
1. Редактируем строку `SCHEDULE`.
2. Airflow **сам подхватит изменения** в течение ~30 секунд — перезапуск не нужен.
3. В UI (`http://localhost:8080`) открывам DAG → убедимся, что в поле
   *Schedule* отображается новое значение.
4. Если DAG сейчас в состоянии `paused`, запускаем DAG.

## Проверка данных вручную

### CRM
```bash
docker exec -it postgres-crm psql -U crm_user -d crm \
  -c "SELECT id, full_name, serial_number FROM clients LIMIT 5;"
```

### Телеметрия
```bash
docker exec -it postgres-telemetry psql -U telemetry_user -d telemetry \
  -c "SELECT serial_number, event_type, battery_level FROM telemetry LIMIT 5;"
```

### Витрина ClickHouse
```bash
docker exec -it clickhouse clickhouse-client \
  --query "SELECT client_id, full_name, total_events, avg_battery_level, error_events
           FROM mart.client_telemetry_analytics ORDER BY client_id LIMIT 5"
```

## Структура витрины ClickHouse

**`mart.telemetry_events`** — сырые события телеметрии, `ORDER BY (serial_number, event_time)`.

**`mart.client_telemetry_analytics`** — витрина «клиент + агрегаты телеметрии»:

| Поле               | Тип          | Описание                          |
|--------------------|--------------|-----------------------------------|
| client_id          | UInt32       | ID клиента из CRM                 |
| full_name          | String       | ФИО                               |
| email, username    | String       | Контакты                          |
| prosthesis_type    | String       | Тип протеза                       |
| prosthesis_model   | String       | Модель                            |
| serial_number      | String       | Серийный номер                    |
| order_number       | String       | Номер заказа                      |
| order_price        | Decimal(12,2)| Стоимость заказа                  |
| install_date       | Date         | Дата установки                    |
| total_events       | UInt32       | Всего событий телеметрии          |
| avg_response_time  | Float64      | Средний отклик, мс                |
| avg_battery_level  | Float64      | Средний заряд батареи, %          |
| avg_signal_quality | Float64      | Среднее качество сигнала, %       |
| error_events       | UInt32       | Кол-во событий с error_code       |
| last_event_time    | DateTime     | Время последнего события          |
| updated_at         | DateTime     | Момент последней пересборки витрины |

Ключ сортировки `ORDER BY (client_id, serial_number)` обеспечивает
быструю выборку всех данных конкретного клиента.