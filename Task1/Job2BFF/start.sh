#!/usr/bin/env bash
set -e

# Переходим в директорию скрипта, чтобы пути работали из любого места
cd "$(dirname "$0")"

# Определяем команду docker compose: v2 (плагин) или v1 (бинарь)
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif docker-compose version >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "ERROR: neither 'docker compose' nor 'docker-compose' found"
  exit 1
fi

echo "Using: $DC"

echo "1. Stopping and removing existing containers/volumes..."
$DC down -v

echo "2. Building and starting services..."
$DC up --build -d

echo "3. Waiting for Keycloak (realm: reports-realm)..."
for i in $(seq 1 60); do
  if curl -fsS http://localhost:8080/realms/reports-realm > /dev/null 2>&1; then
    echo "   Keycloak is ready."
    break
  fi
  if [ "$i" -eq 60 ]; then
    echo "ERROR: Keycloak did not start within timeout."
    $DC logs keycloak | tail -n 50
    exit 1
  fi
  sleep 2
done

echo "4. Waiting for BFF (/health)..."
for i in $(seq 1 60); do
  if curl -fsS http://localhost:8000/health > /dev/null 2>&1; then
    echo "   BFF is ready."
    break
  fi
  if [ "$i" -eq 60 ]; then
    echo "ERROR: BFF did not start within timeout."
    $DC logs bff | tail -n 50
    exit 1
  fi
  sleep 2
done

echo "5. Waiting for Frontend (http://localhost:3000)..."
for i in $(seq 1 30); do
  if curl -fsS http://localhost:3000 > /dev/null 2>&1; then
    echo "   Frontend is ready."
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "WARN: Frontend not responding, but continuing."
    break
  fi
  sleep 2
done

echo ""
echo "==============================================="
echo " All services are up:"
echo "   Frontend : http://localhost:3000"
echo "   BFF      : http://localhost:8000"
echo "   Keycloak : http://localhost:8080"
echo "   Admin    : http://localhost:8080/admin (admin/admin)"
echo "==============================================="
echo ""
echo "Next steps:"
echo "  ./test-xss.sh        # run XSS/security checks"
echo "  $DC logs -f          # tail logs"
