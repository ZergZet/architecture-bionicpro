#!/usr/bin/env bash
set -euo pipefail

KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:8081}"
REALM="${REALM:-reports-realm}"
CLI_CLIENT="${CLI_CLIENT:-reports-cli}"
API_URL="${API_URL:-http://localhost:8000}"

PASS="\e[32mPASS\e[0m"
FAIL="\e[31mFAIL\e[0m"
errors=0

ok()   { echo -e "  ${PASS}  $1"; }
bad()  { echo -e "  ${FAIL}  $1"; errors=$((errors+1)); }
info() { echo -e "\e[94mINFO\e[0m  $1"; }

get_token() {
    local user="$1" pass="$2"
    curl -sS -X POST "${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/token" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        --data-urlencode "grant_type=password" \
        --data-urlencode "client_id=${CLI_CLIENT}" \
        --data-urlencode "username=${user}" \
        --data-urlencode "password=${pass}" \
        | python3 -c 'import sys,json;print(json.load(sys.stdin).get("access_token",""))'
}

check_status() {
    local url="$1"; shift
    curl -s -o /tmp/_body -w "%{http_code}" "$@" "$url"
}

echo "==> Ожидание Keycloak и Reports API"
for _ in $(seq 1 60); do
    curl -fsS "${KEYCLOAK_URL}/realms/${REALM}/.well-known/openid-configuration" >/dev/null 2>&1 && break
    sleep 2
done
for _ in $(seq 1 60); do
    curl -fsS "${API_URL}/health" >/dev/null 2>&1 && break
    sleep 2
done

info "Получаем токены для user_1, user_2, admin1"
TOKEN_U1="$(get_token user_1 password123)"
TOKEN_U2="$(get_token user_2 password123)"
TOKEN_ADMIN="$(get_token admin1 admin123)"

[ -n "$TOKEN_U1" ] && ok "Токен user_1 получен" || bad "Токен user_1 не получен"
[ -n "$TOKEN_U2" ] && ok "Токен user_2 получен" || bad "Токен user_2 не получен"
[ -n "$TOKEN_ADMIN" ] && ok "Токен admin1 получен" || bad "Токен admin1 не получен"

code=$(check_status "${API_URL}/reports")
if [ "$code" = "401" ]; then ok "GET /reports без токена -> 401"; else bad "GET /reports без токена: ожидали 401, получили $code"; fi

code=$(check_status "${API_URL}/reports" -H "Authorization: Bearer invalid.token.value")
if [ "$code" = "401" ]; then ok "GET /reports с невалидным токеном -> 401"; else bad "GET /reports невалидный токен: ожидали 401, получили $code"; fi

code=$(check_status "${API_URL}/reports" -H "Authorization: Bearer ${TOKEN_U1}")
if [ "$code" = "200" ]; then ok "GET /reports (user_1) -> 200"; else bad "GET /reports (user_1): ожидали 200, получили $code"; fi

BODY_U1="$(cat /tmp/_body)"
U1_USERNAME=$(echo "$BODY_U1" | python3 -c 'import sys,json;print(json.load(sys.stdin)["user"]["username"])' 2>/dev/null || echo "")
if [ "$U1_USERNAME" = "user_1" ]; then ok "Отчёт содержит username=user_1"; else bad "Отчёт содержит username='$U1_USERNAME', ожидали user_1"; fi

U1_ID=$(echo "$BODY_U1" | python3 -c 'import sys,json;print(json.load(sys.stdin)["user"]["client_id"])' 2>/dev/null || echo "")
code=$(check_status "${API_URL}/reports?user_id=${U1_ID}" -H "Authorization: Bearer ${TOKEN_U1}")
if [ "$code" = "200" ]; then ok "GET /reports?user_id=<own> (user_1) -> 200"; else bad "GET /reports?user_id=<own>: ожидали 200, получили $code"; fi

code=$(check_status "${API_URL}/reports" -H "Authorization: Bearer ${TOKEN_U2}")
BODY_U2="$(cat /tmp/_body)"
U2_ID=$(echo "$BODY_U2" | python3 -c 'import sys,json;print(json.load(sys.stdin)["user"]["client_id"])' 2>/dev/null || echo "")
if [ -n "$U2_ID" ] && [ "$U2_ID" != "$U1_ID" ]; then
    code=$(check_status "${API_URL}/reports?user_id=${U2_ID}" -H "Authorization: Bearer ${TOKEN_U1}")
    if [ "$code" = "403" ]; then ok "user_1 -> отчёт user_2 по user_id -> 403"; else bad "user_1 -> отчёт user_2: ожидали 403, получили $code"; fi
else
    info "Пропускаю проверку 403 (не удалось получить user_2 client_id)"
fi

code=$(check_status "${API_URL}/reports/users" -H "Authorization: Bearer ${TOKEN_U1}")
if [ "$code" = "403" ]; then ok "GET /reports/users (user_1) -> 403"; else bad "GET /reports/users (user_1): ожидали 403, получили $code"; fi

code=$(check_status "${API_URL}/reports/users?limit=5" -H "Authorization: Bearer ${TOKEN_ADMIN}")
if [ "$code" = "200" ]; then ok "GET /reports/users (admin1) -> 200"; else bad "GET /reports/users (admin1): ожидали 200, получили $code"; fi

info "Проверка отсутствия данных за период"
code=$(check_status "${API_URL}/reports?from=1970-01-01&to=1970-01-02" -H "Authorization: Bearer ${TOKEN_U1}")
if [ "$code" = "200" ]; then ok "GET /reports?from=1970-01-01&to=1970-01-02 -> 200"; else bad "Пустой период: ожидали 200, получили $code"; fi

BODY=$(cat /tmp/_body)
AVAIL=$(echo "$BODY" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("available"))' 2>/dev/null || echo "")
if [ "$AVAIL" = "False" ]; then ok "available=false для пустого периода"; else bad "available=$AVAIL, ожидали False"; fi

MSG=$(echo "$BODY" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("message",""))' 2>/dev/null || echo "")
if echo "$MSG" | grep -q "Данные за указанный период недоступны"; then
    ok "message содержит «Данные за указанный период недоступны»"
else
    bad "message='$MSG', ожидали текст про недоступный период"
fi

code=$(check_status "${API_URL}/reports?from=not-a-date" -H "Authorization: Bearer ${TOKEN_U1}")
if [ "$code" = "422" ]; then ok "GET /reports?from=not-a-date -> 422"; else bad "Некорректная дата: ожидали 422, получили $code"; fi

code=$(check_status "${API_URL}/reports?from=2020-01-01" -H "Authorization: Bearer ${TOKEN_U1}")
if [ "$code" = "200" ]; then ok "GET /reports?from=2020-01-01 -> 200"; else bad "Только from: ожидали 200, получили $code"; fi

echo
if [ "$errors" -gt 0 ]; then
    echo -e "${FAIL}  Провалено проверок: $errors"
    exit 1
fi
echo -e "${PASS}  Все проверки пройдены успешно."
