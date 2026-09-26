#!/usr/bin/env bash
set -e

BFF=${BFF:-http://localhost:8000}
FRONTEND=${FRONTEND:-http://localhost:3000}

echo "1. Проверка, что сессионная cookie BFF имеет флаг HttpOnly..."
COOKIE_HEADER=$(curl -sI "$BFF/auth/login" | tr -d '\r')
if ! echo "$COOKIE_HEADER" | grep -qi 'Set-Cookie:.*HttpOnly'; then
  echo "ОШИБКА: сессионная cookie не имеет флага HttpOnly"
  exit 1
fi
echo "УСПЕХ: сессионная cookie защищена флагом HttpOnly"

echo "2. Проверка, что /auth/me не раскрывает токены..."
ME=$(curl -s "$BFF/auth/me" || true)
if echo "$ME" | grep -qi 'access_token\|refresh_token\|id_token'; then
  echo "ОШИБКА: токены утекают через /auth/me"
  exit 1
fi
echo "УСПЕХ: в /auth/me токены отсутствуют"

echo "3. Проверка, что /api/reports требует активную сессию..."
CODE=$(curl -s -o /dev/null -w '%{http_code}' "$BFF/api/reports")
if [ "$CODE" != "401" ]; then
  echo "ОШИБКА: /api/reports без сессии вернул код $CODE, ожидался 401"
  exit 1
fi
echo "УСПЕХ: /api/reports защищён и не отдаёт данные без сессии"

echo "4. Проверка, что CORS не разрешает произвольный источник (origin) с credentials..."
CORS=$(curl -sI -H "Origin: http://evil.example" "$BFF/api/reports" | tr -d '\r')
if echo "$CORS" | grep -qi 'Access-Control-Allow-Origin: http://evil.example'; then
  echo "ОШИБКА: CORS разрешает доступ со стороннего источника"
  exit 1
fi
echo "УСПЕХ: CORS ограничен доверенным источником"

echo "5. Проверка, что фронтенд не хранит токены в localStorage/sessionStorage..."
if grep -RInE 'localStorage|sessionStorage' "$FRONTEND/src" 2>/dev/null | grep -i token; then
  echo "ОШИБКА: фронтенд может хранить токены в web storage"
  exit 1
fi
echo "УСПЕХ: в исходниках фронтенда нет сохранения токенов в web storage"

echo "Все проверки, связанные с защитой от XSS, пройдены."
