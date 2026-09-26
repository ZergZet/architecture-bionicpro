

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
Job2/
├── docker-compose.yml
├── start.sh
├── test_reports.py
├── test_reports.sh
├── README.md
├── reports/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       └── main.py
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
# Стек: CRM + Телеметрия + ClickHouse-витрина + Airflow + Reports API

## Что разворачивается

| Сервис                 | Порт (host)  | URL / Креды                                          |
|------------------------|--------------|------------------------------------------------------|
| PostgreSQL — CRM       | 5433         | `crm_user` / `crm_pass` / БД `crm`                   |
| PostgreSQL — Telemetry | 5434         | `telemetry_user` / `telemetry_pass` / БД `telemetry` |
| PostgreSQL — Airflow   | (внутренний) | `airflow` / `airflow` / БД `airflow`                 |
| ClickHouse             | 8123 / 9000  | `default` без пароля, БД `mart`                      |
| Airflow UI             | 8080         | http://localhost:8080 (`admin` / `admin`)            |
| Reports API            | 8000         | http://localhost:8000/reports                        |

## Запуск

```bash
chmod +x start.sh test_reports.sh test_reports.py
./start.sh
```

Скрипт:
1. Создаёт каталоги `airflow/{dags,logs,plugins}` и выставляет владельца UID 50000.
2. Собирает образ Airflow и Reports, поднимает 7 контейнеров.
3. Дожидается завершения `airflow-init` и готовности Airflow UI и Reports API.
4. Печатает статус и адреса.

## Полный сброс

```bash
docker compose down -v
./start.sh
```

## Reports API

### Эндпоинты

| Метод | Путь                   | Описание                                                       |
|-------|------------------------|----------------------------------------------------------------|
| GET   | `/health`              | Проверка живости + доступности ClickHouse                      |
| GET   | `/reports/users`       | Список доступных `client_id` из витрины                        |
| GET   | `/reports?user_id=N`   | Полный отчёт по клиенту с `client_id=N`                        |

Отчёт формируется из готовой витрины `mart.client_telemetry_analytics` без тяжёлых
вычислений на лету. Дополнительно подтягивается разбивка событий по типам из
`mart.telemetry_events` — лёгкий агрегат ClickHouse.

### Пример

```bash
curl -s "http://localhost:8000/reports/users"    | python3 -m json.tool
curl -s "http://localhost:8000/reports?user_id=1" | python3 -m json.tool
```

### Тест

```bash
./test_reports.sh
```

Проверяет: `/health`, `/reports/users`, отчёты по двум клиентам, 404 на несуществующего,
422 на некорректный и отсутствующий параметр.

## Изменение расписания сбора данных

Файл `airflow/dags/crm_telemetry_mart.py`:

```python
SCHEDULE = "*/5 * * * *"
```

| Значение       | Что значит                     |
|----------------|--------------------------------|
| `*/5 * * * *`  | каждые 5 минут (по умолчанию)  |
| `*/10 * * * *` | каждые 10 минут                |
| `0 * * * *`    | каждый час                     |
| `0 6 * * *`    | каждый день в 06:00            |
| `@hourly`      | каждый час                     |

Airflow подхватит изменения автоматически за ~30 секунд.

## Проверка данных

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

**`mart.telemetry_events`** — сырые события телеметрии (`ORDER BY serial_number, event_time`).

**`mart.client_telemetry_analytics`** — витрина «клиент + агрегаты телеметрии»:

| Поле               | Тип          | Описание                     |
|--------------------|--------------|------------------------------|
| client_id          | UInt32       | ID клиента из CRM            |
| full_name          | String       | ФИО                          |
| email, username    | String       | Контакты                     |
| prosthesis_type    | String       | Тип протеза                  |
| prosthesis_model   | String       | Модель                       |
| serial_number      | String       | Серийный номер               |
| order_number       | String       | Номер заказа                 |
| order_price        | Decimal(12,2)| Стоимость заказа             |
| install_date       | Date         | Дата установки               |
| total_events       | UInt32       | Всего событий телеметрии     |
| avg_response_time  | Float64      | Средний отклик, мс           |
| avg_battery_level  | Float64      | Средний заряд батареи, %     |
| avg_signal_quality | Float64      | Среднее качество сигнала, %  |
| error_events       | UInt32       | Кол-во событий с error_code  |
| last_event_time    | DateTime     | Время последнего события     |
| updated_at         | DateTime     | Момент последней пересборки  |