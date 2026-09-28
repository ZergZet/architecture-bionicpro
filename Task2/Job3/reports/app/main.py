from __future__ import annotations

import os
from typing import Any

import clickhouse_connect
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

CH_HOST     = os.getenv("CLICKHOUSE_HOST", "clickhouse")
CH_PORT     = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CH_USER     = os.getenv("CLICKHOUSE_USER", "default")
CH_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")
CH_DATABASE = os.getenv("CLICKHOUSE_DATABASE", "mart")

app = FastAPI(
    title="Prosthetics Reports Service",
    version="1.0.0",
    description="API отчётов по клиенту на основе витрины ClickHouse",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _ch():
    return clickhouse_connect.get_client(
        host=CH_HOST,
        port=CH_PORT,
        username=CH_USER,
        password=CH_PASSWORD,
        database=CH_DATABASE,
    )


@app.get("/health")
def health() -> dict[str, str]:
    try:
        _ch().command("SELECT 1")
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"clickhouse unavailable: {exc}")


@app.get("/reports/users")
def list_users(limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
    rows = _ch().query(
        """
        SELECT client_id, full_name, serial_number
        FROM client_telemetry_analytics
        ORDER BY client_id
        LIMIT {lim:UInt32}
        """,
        parameters={"lim": limit},
    ).result_rows

    return {
        "count": len(rows),
        "users": [
            {"client_id": r[0], "full_name": r[1], "serial_number": r[2]}
            for r in rows
        ],
    }


@app.get("/reports")
def get_report(
    user_id: int = Query(..., description="ID клиента (client_id из витрины)", ge=1),
) -> dict[str, Any]:
    ch = _ch()

    rows = ch.query(
        """
        SELECT client_id, full_name, email, username,
               prosthesis_type, prosthesis_model, serial_number,
               order_number, order_price, install_date,
               total_events, avg_response_time, avg_battery_level,
               avg_signal_quality, error_events, last_event_time, updated_at
        FROM client_telemetry_analytics
        WHERE client_id = {uid:UInt32}
        """,
        parameters={"uid": user_id},
    ).result_rows

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"Отчёт для client_id={user_id} не найден",
        )

    r = rows[0]
    serial_number = r[6]

    breakdown_rows = ch.query(
        """
        SELECT event_type, count() AS cnt
        FROM telemetry_events
        WHERE serial_number = {sn:String}
        GROUP BY event_type
        ORDER BY cnt DESC
        """,
        parameters={"sn": serial_number},
    ).result_rows

    return {
        "user": {
            "client_id": r[0],
            "full_name": r[1],
            "email": r[2],
            "username": r[3],
            "prosthesis_type": r[4],
            "prosthesis_model": r[5],
            "serial_number": r[6],
            "order_number": r[7],
            "order_price": float(r[8]),
            "install_date": r[9].isoformat() if r[9] else None,
        },
        "telemetry_summary": {
            "total_events": int(r[10]),
            "avg_response_time_ms": round(float(r[11]), 2),
            "avg_battery_level_pct": round(float(r[12]), 2),
            "avg_signal_quality_pct": round(float(r[13]), 2),
            "error_events": int(r[14]),
            "last_event_time": r[15].isoformat() if r[15] else None,
        },
        "event_breakdown": [
            {"event_type": et, "count": int(cnt)} for et, cnt in breakdown_rows
        ],
        "generated_at": r[16].isoformat() if r[16] else None,
    }