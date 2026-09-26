"""
DAG собирает витрину ClickHouse из двух источников:
  - crm_db        (PostgreSQL, таблица clients)
  - telemetry_db  (PostgreSQL, таблица telemetry)

Логика:
  1) Полный сброс и загрузка сырых событий в mart.telemetry_events
  2) Расчёт агрегатов по каждому протезу (серийному номеру)
  3) Сброс и загрузка агрегатов в mart.client_telemetry_analytics

Расписание по умолчанию: каждые 5 минут (*/5 * * * *).
Как менять расписание — см. README.md.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

import clickhouse_connect
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook

# ---------- Параметры ClickHouse ----------
CH_HOST     = "clickhouse"
CH_PORT     = 8123
CH_USER     = "default"
CH_PASSWORD = ""
CH_DATABASE = "mart"

# ---------- Расписание (менять здесь) ----------
SCHEDULE = "*/5 * * * *"   # раз в 5 минут


default_args = {
    "owner": "data-platform",
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
}


def _ch_client():
    return clickhouse_connect.get_client(
        host=CH_HOST,
        port=CH_PORT,
        username=CH_USER,
        password=CH_PASSWORD,
        database=CH_DATABASE,
    )


def build_mart() -> None:
    crm_hook = PostgresHook(postgres_conn_id="crm_db")
    tel_hook = PostgresHook(postgres_conn_id="telemetry_db")

    clients = crm_hook.get_records(
        """
        SELECT id, full_name, email, username,
               prosthesis_type, prosthesis_model,
               serial_number, order_number, order_price, install_date
        FROM clients
        ORDER BY id
        """
    )

    telemetry = tel_hook.get_records(
        """
        SELECT serial_number, event_type, event_time,
               response_time_ms, battery_level, signal_quality, error_code
        FROM telemetry
        """
    )

    ch = _ch_client()

    # ---------- 1. Сырые события ----------
    ch.command("TRUNCATE TABLE IF EXISTS mart.telemetry_events")
    if telemetry:
        rows = [
            (
                r[0] or "",
                r[1] or "",
                r[2].replace(tzinfo=None) if r[2] else None,
                float(r[3] or 0),
                float(r[4] or 0),
                float(r[5] or 0),
                r[6] or "",
            )
            for r in telemetry
        ]
        ch.insert(
            "telemetry_events",
            rows,
            column_names=[
                "serial_number", "event_type", "event_time",
                "response_time_ms", "battery_level",
                "signal_quality", "error_code",
            ],
        )

    # ---------- 2. Агрегация ----------
    agg: dict[str, dict] = defaultdict(
        lambda: {"total": 0, "resp": 0.0, "bat": 0.0, "sig": 0.0,
                 "errors": 0, "last": None}
    )
    for sn, _etype, etime, resp, bat, sig, err in telemetry:
        a = agg[sn]
        a["total"] += 1
        a["resp"]  += float(resp or 0)
        a["bat"]   += float(bat or 0)
        a["sig"]   += float(sig or 0)
        if err:
            a["errors"] += 1
        if etime and (a["last"] is None or etime > a["last"]):
            a["last"] = etime

    # ---------- 3. Витрина ----------
    now = datetime.utcnow()
    mart_rows = []
    for c in clients:
        cid, full_name, email, username, ptype, pmodel, \
            sn, onum, price, idate = c
        a = agg.get(sn)
        if not a or a["total"] == 0:
            continue
        mart_rows.append((
            int(cid),
            full_name or "",
            email or "",
            username or "",
            ptype or "",
            pmodel or "",
            sn or "",
            onum or "",
            float(price or 0),
            idate,
            a["total"],
            a["resp"] / a["total"],
            a["bat"]  / a["total"],
            a["sig"]  / a["total"],
            a["errors"],
            a["last"].replace(tzinfo=None) if a["last"] else None,
            now,
        ))

    ch.command("TRUNCATE TABLE IF EXISTS mart.client_telemetry_analytics")
    if mart_rows:
        ch.insert(
            "client_telemetry_analytics",
            mart_rows,
            column_names=[
                "client_id", "full_name", "email", "username",
                "prosthesis_type", "prosthesis_model", "serial_number",
                "order_number", "order_price", "install_date",
                "total_events", "avg_response_time", "avg_battery_level",
                "avg_signal_quality", "error_events", "last_event_time",
                "updated_at",
            ],
        )


with DAG(
    dag_id="crm_telemetry_mart",
    description="Сборка витрины ClickHouse из CRM и телеметрии",
    start_date=datetime(2024, 1, 1),
    schedule=SCHEDULE,
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["mart", "crm", "telemetry", "clickhouse"],
) as dag:

    build_mart_task = PythonOperator(
        task_id="build_mart",
        python_callable=build_mart,
    )