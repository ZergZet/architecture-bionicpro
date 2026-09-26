#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

API_URL="${BASE_URL:-http://localhost:8000}"

echo "==> Проверяю, что сервис отчётов доступен по ${API_URL}"
for _ in $(seq 1 30); do
    if curl -fsS "${API_URL}/health" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

if ! curl -fsS "${API_URL}/health" >/dev/null 2>&1; then
    echo "!!! ${API_URL}/health недоступен."
    echo "    Убедитесь, что стек запущен:  ./start.sh"
    echo "    И что DAG 'crm_telemetry_mart' уже отработал хотя бы раз:"
    echo "      docker exec -it airflow-scheduler airflow dags trigger crm_telemetry_mart"
    exit 1
fi

echo "==> Запускаю test_reports.py"
echo

if command -v python3 >/dev/null 2>&1; then
    BASE_URL="${API_URL}" python3 test_reports.py
else
    echo "python3 не найден на хосте. Запускаю тест внутри контейнера reports:"
    docker exec -i -e BASE_URL="http://localhost:8000" reports \
        python3 - < test_reports.py
fi