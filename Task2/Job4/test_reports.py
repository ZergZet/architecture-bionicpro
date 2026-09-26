#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API_URL      = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8081").rstrip("/")
REALM        = os.getenv("REALM", "reports-realm")
CLI_CLIENT   = os.getenv("CLI_CLIENT", "reports-cli")

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
INFO = "\033[94mINFO\033[0m"

errors: list[str] = []


def _http(method: str, url: str, *, data=None, headers=None):
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode()
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, body
    except urllib.error.URLError as exc:
        print(f"{FAIL}  connection error to {url}: {exc}")
        sys.exit(2)


def get_token(username: str, password: str) -> str:
    payload = urllib.parse.urlencode({
        "grant_type": "password",
        "client_id": CLI_CLIENT,
        "username": username,
        "password": password,
    }).encode()
    code, body = _http(
        "POST",
        f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if code != 200 or not isinstance(body, dict):
        return ""
    return body.get("access_token", "")


def check(name: str, cond: bool, extra: str = "") -> None:
    if cond:
        print(f"  {PASS}  {name}")
    else:
        print(f"  {FAIL}  {name}  {extra}")
        errors.append(name)


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    print(f"{INFO}  API_URL = {API_URL}")
    print(f"{INFO}  KEYCLOAK_URL = {KEYCLOAK_URL}  realm = {REALM}")

    section("1. Health-check Reports API")
    code, body = _http("GET", f"{API_URL}/health")
    check("GET /health -> 200", code == 200, f"(code {code})")
    check("status == ok", isinstance(body, dict) and body.get("status") == "ok", str(body))

    section("2. Получение токенов Keycloak")
    tok_u1 = get_token("user_1", "password123")
    tok_u2 = get_token("user_2", "password123")
    tok_admin = get_token("admin1", "admin123")
    check("token user_1", bool(tok_u1))
    check("token user_2", bool(tok_u2))
    check("token admin1", bool(tok_admin))
    if not (tok_u1 and tok_u2 and tok_admin):
        print(f"\n{FAIL}  не удалось получить токены — проверьте Keycloak")
        return 1

    section("3. /reports без токена → 401")
    code, _ = _http("GET", f"{API_URL}/reports")
    check("GET /reports (no auth) -> 401", code == 401, f"(code {code})")

    section("4. /reports с невалидным токеном → 401")
    code, _ = _http("GET", f"{API_URL}/reports",
                    headers={"Authorization": "Bearer not-a-jwt"})
    check("GET /reports (invalid) -> 401", code == 401, f"(code {code})")

    section("5. /reports с токеном user_1 → 200 + свой username")
    code, body = _http("GET", f"{API_URL}/reports",
                       headers={"Authorization": f"Bearer {tok_u1}"})
    check("GET /reports (user_1) -> 200", code == 200, f"(code {code})")
    if isinstance(body, dict):
        uname = body.get("user", {}).get("username")
        check("username == user_1", uname == "user_1", str(uname))
        check("available == True", body.get("available") is True, str(body.get("available")))
    else:
        check("ответ — JSON", False, str(body))

    u1_id = body.get("user", {}).get("client_id") if isinstance(body, dict) else None

    section("6. /reports?user_id=<own> → 200")
    if u1_id is not None:
        code, _ = _http("GET", f"{API_URL}/reports?user_id={u1_id}",
                        headers={"Authorization": f"Bearer {tok_u1}"})
        check("GET /reports?user_id=<own> -> 200", code == 200, f"(code {code})")

    section("7. /reports?user_id=<чужой> → 403")
    code, body_u2 = _http("GET", f"{API_URL}/reports",
                          headers={"Authorization": f"Bearer {tok_u2}"})
    u2_id = body_u2.get("user", {}).get("client_id") if isinstance(body_u2, dict) else None
    if u2_id is not None and u2_id != u1_id:
        code, _ = _http("GET", f"{API_URL}/reports?user_id={u2_id}",
                        headers={"Authorization": f"Bearer {tok_u1}"})
        check("GET /reports?user_id=<foreign> -> 403", code == 403, f"(code {code})")

    section("8. /reports/users (user_1) → 403; (admin1) → 200")
    code, _ = _http("GET", f"{API_URL}/reports/users",
                    headers={"Authorization": f"Bearer {tok_u1}"})
    check("/reports/users (user_1) -> 403", code == 403, f"(code {code})")

    code, body = _http("GET", f"{API_URL}/reports/users?limit=5",
                       headers={"Authorization": f"Bearer {tok_admin}"})
    check("/reports/users (admin1) -> 200", code == 200, f"(code {code})")
    if isinstance(body, dict):
        check("count > 0", body.get("count", 0) > 0, str(body.get("count")))

    section("9. Пустой период → available=false + message")
    code, body = _http("GET", f"{API_URL}/reports?from=1970-01-01&to=1970-01-02",
                       headers={"Authorization": f"Bearer {tok_u1}"})
    check("GET /reports?from=1970-01-01&to=1970-01-02 -> 200", code == 200, f"(code {code})")
    if isinstance(body, dict):
        check("available == False", body.get("available") is False, str(body.get("available")))
        msg = body.get("message", "")
        check(
            "message содержит «Данные за указанный период недоступны»",
            "Данные за указанный период недоступны" in msg,
            msg,
        )
        check("period.from корректен",
              (body.get("period") or {}).get("from") == "1970-01-01",
              str(body.get("period")))

    section("10. Некорректный формат даты → 422")
    code, _ = _http("GET", f"{API_URL}/reports?from=not-a-date",
                    headers={"Authorization": f"Bearer {tok_u1}"})
    check("GET /reports?from=not-a-date -> 422", code == 422, f"(code {code})")

    section("11. Только from (без to) → 200")
    code, body = _http("GET", f"{API_URL}/reports?from=2020-01-01",
                       headers={"Authorization": f"Bearer {tok_u1}"})
    check("GET /reports?from=2020-01-01 -> 200", code == 200, f"(code {code})")
    if isinstance(body, dict):
        check("ответ содержит available (bool)",
              isinstance(body.get("available"), bool),
              str(type(body.get("available"))))

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