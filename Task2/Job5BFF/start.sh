#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

mkdir -p airflow/logs airflow/plugins airflow/dags

if [ "$(id -u)" -eq 0 ]; then
    chown -R 50000:0 airflow/logs airflow/plugins
elif command -v sudo >/dev/null 2>&1; then
    sudo chown -R 50000:0 airflow/logs airflow/plugins || true
fi

if grep -qE '^version:' docker-compose.yml 2>/dev/null; then
    sed -i.bak '/^version:/d' docker-compose.yml
fi

echo "==> Сборка образов и запуск контейнеров..."
docker compose up -d --build

echo ""
echo "==> Ожидание завершения airflow-init..."
INIT_OK=""
for _ in $(seq 1 60); do
    STATUS="$(docker inspect -f '{{.State.Status}}' airflow-init 2>/dev/null || echo 'unknown')"
    EXIT_CODE="$(docker inspect -f '{{.State.ExitCode}}' airflow-init 2>/dev/null || echo '')"
    case "$STATUS" in
        exited)
            if [ "$EXIT_CODE" = "0" ]; then INIT_OK="yes"; else INIT_OK="no"; fi
            break
            ;;
        *) sleep 2 ;;
    esac
done

if [ "$INIT_OK" != "yes" ]; then
    echo ""
    echo "!!! airflow-init завершился с ошибкой. Последние строки лога:"
    echo "-------------------------------------------------------------------"
    docker compose logs --tail=200 airflow-init || true
    echo "-------------------------------------------------------------------"
    exit 1
fi

echo "==> airflow-init OK"

echo "==> Ожидание готовности Airflow Web UI..."
for _ in $(seq 1 60); do
    curl -fsS http://localhost:8080/health >/dev/null 2>&1 && break
    sleep 2
done

echo "==> Ожидание готовности BFF..."
for _ in $(seq 1 60); do
    curl -fsS http://localhost:8000/health >/dev/null 2>&1 && break
    sleep 2
done

echo "==> Ожидание готовности Reports API..."
for _ in $(seq 1 60); do
    curl -fsS http://localhost:8001/health >/dev/null 2>&1 && break
    sleep 2
done

echo ""
echo "=========================================================================="
echo " Стек успешно запущен:"
echo "   Frontend              : http://localhost:3000"
echo "   BFF (для фронта)      : http://localhost:8000"
echo "   Reports API (debug)   : http://localhost:8001/reports"
echo "   Airflow UI            : http://localhost:8080   (admin / admin)"
echo "   Keycloak              : http://localhost:8081   (admin / admin)"
echo "   ClickHouse HTTP       : http://localhost:8123   (default, без пароля)"
echo "   Postgres CRM          : localhost:5433          (crm_user / crm_pass / crm)"
echo "   Postgres Telemetry    : localhost:5434          (telemetry_user / telemetry_pass / telemetry)"
echo "=========================================================================="
echo ""
docker compose ps
echo ""
echo " Полный сброс: docker compose down -v && ./start.sh"