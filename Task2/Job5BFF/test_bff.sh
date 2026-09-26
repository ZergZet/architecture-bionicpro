#!/usr/bin/env bash
set -euo pipefail

BFF=${BFF:-http://localhost:8000}
FRONTEND=${FRONTEND:-http://localhost:3000}

PASS="\e[32mPASS\e[0m"
FAIL="\e[31mFAIL\e[0m"
errors=0
ok()  { echo -e "  ${PASS}  $1"; }
bad() { echo -e "  ${FAIL}  $1"; errors=$((errors+1)); }

echo "1. Проверка, что cookie сессии BFF имеет флаг HttpOnly..."
HEADER=$(curl -sI "$BFF/auth/login" | tr -d '\r')
if echo "$HEADER" | grep -qi 'Set-Cookie:.*HttpOnly'; then
  ok "Set-Cookie содержит HttpOnly"
else
  bad "cookie сессии без HttpOnly"
fi

echo "2. /auth/me без сессии → 401 и без токенов в теле..."
CODE=$(curl -s -o /tmp/_bff_me -w '%{http_code}' "$BFF/auth/me")
BODY=$(cat /tmp/_bff_me || true)
if [ "$CODE" = "401" ]; then ok "/auth/me → 401"; else bad "/auth/me без сессии вернул $CODE"; fi
if echo "$BODY" | grep -qiE 'access_token|refresh_token|id_token'; then
  bad "в /auth/me утекают токены"
else
  ok "в /auth/me нет токенов"
fi

echo "3. /api/reports без сессии → 401..."
CODE=$(curl -s -o /dev/null -w '%{http_code}' "$BFF/api/reports")
if [ "$CODE" = "401" ]; then ok "/api/reports без сессии → 401"; else bad "/api/reports без сессии → $CODE"; fi

echo "4. CORS не разрешает произвольный origin..."
CORS=$(curl -sI -H "Origin: http://evil.example" "$BFF/api/reports" | tr -d '\r')
if echo "$CORS" | grep -qi 'Access-Control-Allow-Origin: http://evil.example'; then
  bad "CORS разрешает чужой origin"
else
  ok "CORS не разрешает чужой origin"
fi

echo "5. Во фронтенд-исходниках нет хранилищ токенов..."
if grep -RInE 'localStorage|sessionStorage' frontend/src 2>/dev/null | grep -i token; then
  bad "во фронте найдено хранение токенов"
else
  ok "во фронте нет хранения токенов"
fi

echo
if [ "$errors" -gt 0 ]; then
  echo -e "${FAIL}  Провалено проверок: $errors"
  exit 1
fi
echo -e "${PASS}  Все проверки BFF пройдены."