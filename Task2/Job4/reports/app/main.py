from __future__ import annotations

import os
import time
from datetime import date, datetime
from typing import Any

import clickhouse_connect
import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt

# ---------------- ClickHouse ----------------
CH_HOST     = os.getenv("CLICKHOUSE_HOST", "clickhouse")
CH_PORT     = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CH_USER     = os.getenv("CLICKHOUSE_USER", "default")
CH_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")
CH_DATABASE = os.getenv("CLICKHOUSE_DATABASE", "mart")

# ---------------- Keycloak ----------------
KC_INTERNAL_URL = os.getenv("KEYCLOAK_INTERNAL_URL", "http://keycloak:8080")
KC_PUBLIC_URL   = os.getenv("KEYCLOAK_PUBLIC_URL", "http://localhost:8081")
KC_REALM        = os.getenv("KEYCLOAK_REALM", "reports-realm")

JWKS_URL = f"{KC_INTERNAL_URL}/realms/{KC_REALM}/protocol/openid-connect/certs"
ISSUER   = f"{KC_PUBLIC_URL}/realms/{KC_REALM}"

app = FastAPI(title="Prosthetics Reports Service", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _ch():
    return clickhouse_connect.get_client(
        host=CH_HOST, port=CH_PORT,
        username=CH_USER, password=CH_PASSWORD,
        database=CH_DATABASE,
    )


# ---------------- JWKS ----------------
_jwks_cache: dict[str, Any] = {"data": None, "ts": 0.0}
_JWKS_TTL = 300.0


def _get_jwks() -> dict:
    now = time.time()
    if _jwks_cache["data"] is None or (now - _jwks_cache["ts"]) > _JWKS_TTL:
        resp = httpx.get(JWKS_URL, timeout=10.0)
        resp.raise_for_status()
        _jwks_cache["data"] = resp.json()
        _jwks_cache["ts"] = now
    return _jwks_cache["data"]


def _verify_token(authorization: str | None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        jwks = _get_jwks()
        kid = jwt.get_unverified_header(token).get("kid")
        rsa_key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
        if rsa_key is None:
            raise HTTPException(status_code=401, detail="Unknown signing key")
        return jwt.decode(
            token, rsa_key,
            algorithms=["RS256"],
            issuer=ISSUER,
            options={"verify_aud": False},
        )
    except HTTPException:
        raise
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")


def _current_user(authorization: str | None = Header(default=None)) -> dict:
    return _verify_token(authorization)


# ---------------- helpers ----------------
def _lookup_client_id(username: str) -> int | None:
    rows = _ch().query(
        "SELECT client_id FROM client_telemetry_analytics "
        "WHERE username = {u:String} LIMIT 1",
        parameters={"u": username},
    ).result_rows
    return int(rows[0][0]) if rows else None


def _fetch_client_row(client_id: int):
    rows = _ch().query(
        """
        SELECT client_id, full_name, email, username,
               prosthesis_type, prosthesis_model, serial_number,
               order_number, order_price, install_date,
               total_events, avg_response_time, avg_battery_level,
               avg_signal_quality, error_events, last_event_time, updated_at
        FROM client_telemetry_analytics
        WHERE client_id = {uid:UInt32}
        """,
        parameters={"uid": client_id},
    ).result_rows
    return rows[0] if rows else None


def _identity_from_row(r) -> dict:
    return {
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
    }


def _period_dict(from_d: date | None, to_d: date | None) -> dict:
    return {
        "from": from_d.isoformat() if from_d else None,
        "to":   to_d.isoformat()   if to_d   else None,
    }


def _no_data_response(user: dict, period: dict, message: str) -> dict:
    return {
        "available": False,
        "period": period,
        "user": user,
        "telemetry_summary": None,
        "event_breakdown": [],
        "message": message,
        "generated_at": datetime.utcnow().isoformat(),
    }


def _period_where(serial_number: str, from_d: date | None, to_d: date | None):
    where  = "serial_number = {sn:String}"
    params = {"sn": serial_number}
    if from_d is not None:
        where += " AND event_time >= {from_dt:DateTime}"
        params["from_dt"] = datetime.combine(from_d, datetime.min.time())
    if to_d is not None:
        where += " AND event_time <= {to_dt:DateTime}"
        params["to_dt"] = datetime.combine(to_d, datetime.max.time())
    return where, params


def _build_period_summary(serial_number: str, from_d, to_d) -> dict | None:
    where, params = _period_where(serial_number, from_d, to_d)
    rows = _ch().query(
        f"""
        SELECT
            count()                                     AS total_events,
            ifNull(avg(response_time_ms), 0)            AS avg_response_time,
            ifNull(avg(battery_level), 0)               AS avg_battery_level,
            ifNull(avg(signal_quality), 0)              AS avg_signal_quality,
            countIf(error_code != '')                   AS error_events,
            max(event_time)                             AS last_event_time
        FROM telemetry_events
        WHERE {where}
        """,
        parameters=params,
    ).result_rows

    if not rows or int(rows[0][0]) == 0:
        return None
    r = rows[0]
    return {
        "total_events": int(r[0]),
        "avg_response_time_ms": round(float(r[1]), 2),
        "avg_battery_level_pct": round(float(r[2]), 2),
        "avg_signal_quality_pct": round(float(r[3]), 2),
        "error_events": int(r[4]),
        "last_event_time": r[5].isoformat() if r[5] else None,
    }


def _build_breakdown(serial_number: str, from_d, to_d) -> list[dict]:
    where, params = _period_where(serial_number, from_d, to_d)
    rows = _ch().query(
        f"""
        SELECT event_type, count() AS cnt
        FROM telemetry_events
        WHERE {where}
        GROUP BY event_type
        ORDER BY cnt DESC
        """,
        parameters=params,
    ).result_rows
    return [{"event_type": et, "count": int(cnt)} for et, cnt in rows]


def _summary_from_mart_row(r) -> dict:
    return {
        "total_events": int(r[10]),
        "avg_response_time_ms": round(float(r[11]), 2),
        "avg_battery_level_pct": round(float(r[12]), 2),
        "avg_signal_quality_pct": round(float(r[13]), 2),
        "error_events": int(r[14]),
        "last_event_time": r[15].isoformat() if r[15] else None,
    }


# ---------------- core report builder ----------------
def _build_response(
    *,
    user: dict,
    user_id: int | None,
    from_d: date | None,
    to_d: date | None,
) -> dict[str, Any]:
    username = user.get("preferred_username")
    if not username:
        raise HTTPException(status_code=401, detail="No username in token")

    period = _period_dict(from_d, to_d)
    has_period = from_d is not None or to_d is not None

    client_id = _lookup_client_id(username)
    if client_id is None:
        return _no_data_response(
            user={"username": username},
            period=period,
            message=(
                "Данные недоступны: витрина для вашего профиля ещё не заполнена. "
                "Убедитесь, что DAG crm_telemetry_mart уже выполнился."
            ),
        )

    if user_id is not None and user_id != client_id:
        raise HTTPException(
            status_code=403,
            detail=f"Доступ запрещён: можно запрашивать отчёт только по client_id={client_id}",
        )

    row = _fetch_client_row(client_id)
    if row is None:
        return _no_data_response(
            user={"username": username, "client_id": client_id},
            period=period,
            message="Данные недоступны: запись отсутствует в витрине.",
        )

    identity      = _identity_from_row(row)
    serial_number = identity["serial_number"]

    if has_period:
        summary = _build_period_summary(serial_number, from_d, to_d)
        if summary is None:
            return _no_data_response(
                user=identity,
                period=period,
                message="Данные за указанный период недоступны",
            )
        breakdown = _build_breakdown(serial_number, from_d, to_d)
    else:
        if int(row[10]) == 0:
            return _no_data_response(
                user=identity,
                period=period,
                message="Данные в витрине для этого клиента отсутствуют",
            )
        summary   = _summary_from_mart_row(row)
        breakdown = _build_breakdown(serial_number, None, None)

    return {
        "available": True,
        "period": period,
        "user": identity,
        "telemetry_summary": summary,
        "event_breakdown": breakdown,
        "generated_at": datetime.utcnow().isoformat(),
    }


# ---------------- endpoints ----------------
@app.get("/health")
def health() -> dict[str, str]:
    try:
        _ch().command("SELECT 1")
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"clickhouse unavailable: {exc}")


@app.get("/reports")
def get_report(
    user: dict = Depends(_current_user),
    user_id: int | None = Query(None),
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
) -> dict[str, Any]:
    return _build_response(
        user=user, user_id=user_id,
        from_d=from_date, to_d=to_date,
    )


@app.get("/reports/me")
def get_my_report(
    user: dict = Depends(_current_user),
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
) -> dict[str, Any]:
    return _build_response(
        user=user, user_id=None,
        from_d=from_date, to_d=to_date,
    )


@app.get("/reports/users")
def list_users(
    user: dict = Depends(_current_user),
    limit: int = Query(100, ge=1, le=1000),
) -> dict[str, Any]:
    roles = (user.get("realm_access") or {}).get("roles") or []
    if "administrator" not in roles:
        raise HTTPException(status_code=403, detail="Требуется роль administrator")

    rows = _ch().query(
        """
        SELECT client_id, full_name, serial_number, username
        FROM client_telemetry_analytics
        ORDER BY client_id
        LIMIT {lim:UInt32}
        """,
        parameters={"lim": limit},
    ).result_rows

    return {
        "count": len(rows),
        "users": [
            {"client_id": r[0], "full_name": r[1], "serial_number": r[2], "username": r[3]}
            for r in rows
        ],
    }