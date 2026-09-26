#!/usr/bin/env python3
"""
Ручной тест сервиса отчётов.

Проверяет:
  1. /health
  2. /reports/users
  3. /reports?user_id=<первый>
  4. /reports?user_id=<второй>
  5. /reports?user_id=999999  (ожидаем 404)
  6. /reports?user_id=abc     (ожидаем 422)
  7. /reports                 (ожидаем 422)

Запуск:
    python3 test_reports.py
    BASE_URL=http://localhost:8000 python3 test_reports.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
INFO = "\033[94mINFO\033[0m"

errors: list[str] = []


def _request(path: str) -> tuple[int, dict | str | None]:
    url = f"{BASE_URL}{path}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, body
    except urllib.error.URLError as exc:
        print(f"{FAIL}  не удалось подключиться к {url}: {exc}")
        sys.exit(2)


def check(name: str, condition: bool, extra: str = "") -> None:
    if condition:
        print(f"  {PASS}  {name}")
    else:
        print(f"  {FAIL}  {name}  {extra}")
        errors.append(name)


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    print(f"{INFO}  BASE_URL = {BASE_URL}")

    section("1. Health-check")
    code, body = _request("/health")
    check("GET /health -> 200", code == 200, f"(код {code})")
    check("status == ok", isinstance(body, dict) and body.get("status") == "ok", str(body))

    section("2. Список пользователей")
    code, body = _request("/reports/users?limit=5")
    check("GET /reports/users -> 200", code == 200, f"(код {code})")
    users = body.get("users") if isinstance(body, dict) else None
    check("есть список пользователей", isinstance(users, list) and len(users) > 0)

    if not isinstance(users, list) or not users:
        print(f"\n{FAIL}  нет доступных отчётов — сначала прогоните DAG crm_telemetry_mart")
        return 1

    first_id = users[0]["client_id"]
    second_id = users[1]["client_id"] if len(users) > 1 else first_id
    print(f"  {INFO}  первый client_id = {first_id}, второй = {second_id}")

    section(f"3. Отчёт по client_id={first_id}")
    code, body = _request(f"/reports?user_id={first_id}")
    check("GET /reports?user_id -> 200", code == 200, f"(код {code})")

    if isinstance(body, dict):
        user = body.get("user", {})
        summary = body.get("telemetry_summary", {})
        breakdown = body.get("event_breakdown", [])

        check("есть блок 'user'", isinstance(user, dict) and bool(user))
        check("user.client_id совпадает", user.get("client_id") == first_id)
        check("есть ФИО (full_name)", bool(user.get("full_name")))
        check("есть serial_number", bool(user.get("serial_number")))
        check("есть модель протеза", bool(user.get("prosthesis_model")))
        check("есть order_price > 0",
              isinstance(user.get("order_price"), (int, float)) and user["order_price"] > 0)

        check("есть блок 'telemetry_summary'", isinstance(summary, dict) and bool(summary))
        check("total_events > 0",
              isinstance(summary.get("total_events"), int) and summary["total_events"] > 0)
        check("avg_battery_level_pct в [0,100]",
              isinstance(summary.get("avg_battery_level_pct"), (int, float))
              and 0 <= summary["avg_battery_level_pct"] <= 100)
        check("avg_signal_quality_pct в [0,100]",
              isinstance(summary.get("avg_signal_quality_pct"), (int, float))
              and 0 <= summary["avg_signal_quality_pct"] <= 100)
        check("avg_response_time_ms >= 0",
              isinstance(summary.get("avg_response_time_ms"), (int, float))
              and summary["avg_response_time_ms"] >= 0)
        check("есть last_event_time", bool(summary.get("last_event_time")))

        check("есть event_breakdown", isinstance(breakdown, list))
        if isinstance(breakdown, list) and breakdown:
            total_from_breakdown = sum(e.get("count", 0) for e in breakdown)
            check("сумма event_breakdown == total_events",
                  total_from_breakdown == summary.get("total_events"),
                  f"({total_from_breakdown} != {summary.get('total_events')})")

        preview = json.dumps(body, ensure_ascii=False, indent=2)
        print(f"\n  {INFO}  отчёт для {first_id}:")
        print(preview[:1200] + (" …" if len(preview) > 1200 else ""))

    section(f"4. Отчёт по client_id={second_id}")
    code, body = _request(f"/reports?user_id={second_id}")
    check("GET /reports?user_id -> 200", code == 200, f"(код {code})")
    if isinstance(body, dict):
        check("другой серийный номер",
              body.get("user", {}).get("serial_number") != user.get("serial_number")
              or second_id == first_id)

    section("5. Несуществующий пользователь (ожидаем 404)")
    code, body = _request("/reports?user_id=999999")
    check("GET /reports?user_id=999999 -> 404", code == 404, f"(код {code})")

    section("6. Некорректный параметр (ожидаем 422)")
    code, body = _request("/reports?user_id=abc")
    check("GET /reports?user_id=abc -> 422", code == 422, f"(код {code})")

    section("7. Отсутствует user_id (ожидаем 422)")
    code, body = _request("/reports")
    check("GET /reports -> 422", code == 422, f"(код {code})")

    print()
    if errors:
        print(f"{FAIL}  Провалено проверок: {len(errors)}")
        for e in errors:
            print(f"     - {e}")
        return 1

    print(f"{PASS}  Все проверки пройдены успешно.")
    return 0


if __name__ == "__main__":
    sys.exit(main())