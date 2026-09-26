
# Состав: CRM + Телеметрия + ClickHouse + Airflow + Keycloak + Reports + Frontend


# Структура каталогов:

```
Job4_5/
├── docker-compose.yml
├── start.sh
├── test_auth_reports.sh
├── test_reports.py
├── README.md
├── keycloak/
│   └── realm-export.json
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
│   ├── package-lock.json     
│   ├── postcss.config.js
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   ├── public/index.html
│   └── src/
│       ├── index.tsx
│       ├── index.css
│       ├── App.tsx
│       └── components/ReportPage.tsx
├── reports/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/main.py
├── airflow/
│   ├── Dockerfile
│   └── dags/crm_telemetry_mart.py
└── init/
    ├── crm/{01_schema.sql,02_seed.sql}
    ├── telemetry/{01_schema.sql,02_seed.sql}
    └── clickhouse/01_schema.sql
```

## Сброс и запуск

```bash
chmod +x start.sh test_auth_reports.sh test_reports.py
docker compose down -v
./start.sh
```

## Порты и креды

| Сервис                 | Порт (host)  | Адрес/Креды                                          |
|------------------------|--------------|-------------------------------------------------------|
| Frontend (React)       | 3000         | http://localhost:3000                                 |
| Keycloak               | 8081         | http://localhost:8081 (`admin` / `admin`)             |
| Reports API            | 8000         | http://localhost:8000                                 |
| Airflow UI             | 8080         | http://localhost:8080 (`admin` / `admin`)             |
| ClickHouse             | 8123 / 9000  | `default`, без пароля, БД `mart`                      |
| Postgres CRM           | 5433         | `crm_user` / `crm_pass` / БД `crm`                    |
| Postgres Telemetry     | 5434         | `telemetry_user` / `telemetry_pass` / БД `telemetry`  |
| Postgres Keycloak      | (внутренний) | `keycloak_user` / `keycloak_password` / БД `keycloak_db` |


## Аутентификация

- Realm `reports-realm`.
- Клиент `reports-frontend` — публичный, PKCE (`S256`), redirect `http://localhost:3000/*`.
- Клиент `reports-cli` — публичный, password grant, только для тестов.
- Пользователи: `user_1` … `user_50` (пароль `password123`), `admin1` (`admin123`, роль `administrator`).

## Reports API

| Метод | Путь                                     | Доступ                                |
|-------|------------------------------------------|---------------------------------------|
| GET   | `/health`                                | без авторизации                       |
| GET   | `/reports`                               | любой аутентифицированный пользователь|
| GET   | `/reports?from=YYYY-MM-DD&to=YYYY-MM-DD` | то же, с ограничением по периоду      |
| GET   | `/reports?user_id=N`                     | только если N — это ваш client_id     |
| GET   | `/reports/me`                            | алиас `/reports`                      |
| GET   | `/reports/users`                         | только роль `administrator`           |

### Обработка отсутствия данных

Когда данных за указанный период нет, API возвращает **HTTP 200** со структурой:

```json
{
  "available": false,
  "period": { "from": "1970-01-01", "to": "1970-01-02" },
  "user": { "...": "..." },
  "telemetry_summary": null,
  "event_breakdown": [],
  "message": "Данные за указанный период недоступны",
  "generated_at": "..."
}
```

На фронте выводится жёлтая плашка «Данные недоступны → Данные за указанный период недоступны».

## Как проверить вручную

1. Открыть http://localhost:3000 → **Войти через Keycloak**.
2. Войти, например, как `user_1` / `password123`.
3. Нажать **Получить отчёт** → отобразится JSON вашего отчёта.
4. Указать период `1970-01-01 … 1970-01-02` → увидите сообщение «Данные за указанный период недоступны».

## Запуск тестов

```bash
test_auth_reports.sh
```
```bash
python3 test_reports.py
```

Покрытие: 
- получение токенов, 
- отсутствие/невалидность токена, 
- свой отчёт, 
- свой отчёт по `user_id`, 
- попытка чужого отчёта (403), 
- `/reports/users` для обычного пользователя (403) и admin (200), 
- пустой период (`available=false`), 
- некорректный формат даты (422), только `from` без `to`.


## Результ(выборочно)


 <details> <summary> Лог тестов </summary>

![TestsPassed]( .\screens\TestsPassed.png )

 </details>

  <details> <summary> Данные не найдены </summary>

![NoData]( .\screens\NoData.png )

 </details>

  <details> <summary> Отчёт по данным </summary>

![MyReport]( .\screens\MyReport.png )

 </details>


# Пример результата

 <details> <summary> Лог запуска и прогона тестов </summary>

 ```bash
sshuser@astra18zsa-350:~/Desktop/practicum/Sprint9/Task2/Job5BFF$ ./start.sh
==> Сборка образов и запуск контейнеров...
WARN[0000] buildx Docker CLI plugin not found: falling back to the classic builder. BuildKit-only build features (multi-arch, secrets, ssh, additional contexts, ...) will not be available 
Sending build context to Docker daemon  3.955kB
Sending build context to Docker daemon  6.642kB
Step 1/9 : FROM python:3.11-slim
 ---> 274d131132db
Step 2/9 : WORKDIR /app
 ---> Using cache
 ---> b420ef0798a2
Step 3/9 : COPY requirements.txt .
 ---> Using cache
 ---> f7c8f20d166c
Step 4/9 : RUN pip install --no-cache-dir -r requirements.txt
 ---> Using cache
 ---> 20d5b9db7302
Step 5/9 : COPY app/ /app/app/
Step 1/11 : ARG AIRFLOW_VERSION=2.9.3
Step 2/11 : ARG PYTHON_VERSION=3.11
Step 3/11 : ARG AIRFLOW_UID=50000
Step 4/11 : FROM apache/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION}
 ---> Using cache
 ---> 7eae274c9e6f
Step 6/9 : ENV PYTHONUNBUFFERED=1     UVICORN_WORKERS=1
 ---> Using cache
 ---> 32d92d541f2f
Step 7/9 : EXPOSE 8000
 ---> ee1b31e2b8a3
Step 5/11 : ARG AIRFLOW_UID=50000
 ---> Using cache
 ---> b0d419d24c4d
Step 8/9 : CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
 ---> Using cache
 ---> 31c679165152
Step 9/9 : LABEL com.docker.compose.image.builder=classic
 ---> Using cache
 ---> c4dcbec7ba52
Successfully built c4dcbec7ba52
 ---> Using cache
 ---> 01efbe5d96d2
Step 6/11 : ENV AIRFLOW_UID=${AIRFLOW_UID}
Successfully tagged local/reports:1.0.0
 ---> Using cache
 ---> 77e630ef2399
Step 7/11 : USER root
 ---> Using cache
 ---> 2462cfc3a381
Step 8/11 : RUN apt-get update  && apt-get install -y --no-install-recommends         gcc         libpq-dev  && apt-get clean  && rm -rf /var/lib/apt/lists/*
 ---> Using cache
 ---> 666ed5311873
Step 9/11 : USER airflow
 ---> Using cache
 ---> 65cc715dc2a0
Step 10/11 : RUN pip install --no-cache-dir         clickhouse-connect         psycopg2-binary
Sending build context to Docker daemon  2.254kB
 ---> Using cache
 ---> 12c48b3e36dd
Step 11/11 : LABEL com.docker.compose.image.builder=classic
 ---> Using cache
 ---> b2e1be382ca5
Successfully built b2e1be382ca5
Step 1/8 : FROM node:18-alpine
 ---> ee77c6cd7c18
Step 2/8 : WORKDIR /app
Successfully tagged local/airflow-custom:2.9.3
 ---> Using cache
 ---> 896c5771e2d1
Step 3/8 : COPY package*.json ./
 ---> Using cache
 ---> ada8f4d80b83
Step 4/8 : RUN npm install --omit=dev
 ---> Using cache
 ---> f80fce1c83e3
Step 5/8 : COPY server.js .
 ---> Using cache
 ---> 26745ac23419
Step 6/8 : EXPOSE 8000
 ---> Using cache
 ---> 67a282160156
Step 7/8 : CMD ["node", "server.js"]
 ---> Using cache
 ---> 0c0dd768d519
Step 8/8 : LABEL com.docker.compose.image.builder=classic
 ---> Using cache
 ---> 2c9cb5b439f8
Successfully built 2c9cb5b439f8
Successfully tagged local/reports-bff:1.0.0
Sending build context to Docker daemon  6.642kB
Sending build context to Docker daemon  6.642kB
Step 1/11 : ARG AIRFLOW_VERSION=2.9.3
Step 2/11 : ARG PYTHON_VERSION=3.11
Step 3/11 : ARG AIRFLOW_UID=50000
Step 4/11 : FROM apache/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION}
Step 1/11 : ARG AIRFLOW_VERSION=2.9.3
Step 2/11 : ARG PYTHON_VERSION=3.11
Step 3/11 : ARG AIRFLOW_UID=50000
Step 4/11 : FROM apache/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION}
 ---> ee1b31e2b8a3
Step 5/11 : ARG AIRFLOW_UID=50000
 ---> ee1b31e2b8a3
Step 5/11 : ARG AIRFLOW_UID=50000
 ---> Using cache
 ---> 01efbe5d96d2
Step 6/11 : ENV AIRFLOW_UID=${AIRFLOW_UID}
 ---> Using cache
 ---> 01efbe5d96d2
Step 6/11 : ENV AIRFLOW_UID=${AIRFLOW_UID}
 ---> Using cache
 ---> 77e630ef2399
Step 7/11 : USER root
 ---> Using cache
 ---> 77e630ef2399
Step 7/11 : USER root
 ---> Using cache
 ---> 2462cfc3a381
Step 8/11 : RUN apt-get update  && apt-get install -y --no-install-recommends         gcc         libpq-dev  && apt-get clean  && rm -rf /var/lib/apt/lists/*
 ---> Using cache
 ---> 2462cfc3a381
Step 8/11 : RUN apt-get update  && apt-get install -y --no-install-recommends         gcc         libpq-dev  && apt-get clean  && rm -rf /var/lib/apt/lists/*
 ---> Using cache
 ---> 666ed5311873
Step 9/11 : USER airflow
 ---> Using cache
 ---> 666ed5311873
Step 9/11 : USER airflow
 ---> Using cache
 ---> 65cc715dc2a0
Step 10/11 : RUN pip install --no-cache-dir         clickhouse-connect         psycopg2-binary
 ---> Using cache
 ---> 65cc715dc2a0
Step 10/11 : RUN pip install --no-cache-dir         clickhouse-connect         psycopg2-binary
 ---> Using cache
 ---> 12c48b3e36dd
Step 11/11 : LABEL com.docker.compose.image.builder=classic
 ---> Using cache
 ---> 12c48b3e36dd
Step 11/11 : LABEL com.docker.compose.image.builder=classic
 ---> Using cache
 ---> b2e1be382ca5
 ---> Using cache
 ---> b2e1be382ca5
Successfully built b2e1be382ca5
Successfully built b2e1be382ca5
Successfully tagged local/airflow-custom:2.9.3
Successfully tagged local/airflow-custom:2.9.3
Sending build context to Docker daemon    157kB
Step 1/14 : FROM node:18-alpine AS build
 ---> ee77c6cd7c18
Step 2/14 : WORKDIR /app
 ---> Using cache
 ---> 896c5771e2d1
Step 3/14 : COPY package.json ./
 ---> Using cache
 ---> 1269457525a7
Step 4/14 : RUN npm install --legacy-peer-deps
 ---> Using cache
 ---> f93ded84bc26
Step 5/14 : COPY . .
 ---> Using cache
 ---> afbd8c187460
Step 6/14 : ARG REACT_APP_BFF_URL
 ---> Using cache
 ---> 2beef16072e6
Step 7/14 : ENV REACT_APP_BFF_URL=${REACT_APP_BFF_URL}
 ---> Using cache
 ---> 6dcd135cadda
Step 8/14 : RUN npm run build
 ---> Using cache
 ---> cb210c7c3a9f
Step 9/14 : FROM nginx:alpine
 ---> 3dd08163706a
Step 10/14 : COPY --from=build /app/build /usr/share/nginx/html
 ---> Using cache
 ---> 6589f4dbdcb2
Step 11/14 : COPY nginx.conf /etc/nginx/conf.d/default.conf
 ---> Using cache
 ---> f78839fe20de
Step 12/14 : EXPOSE 3000
 ---> Using cache
 ---> 3bf79637b79a
Step 13/14 : CMD ["nginx", "-g", "daemon off;"]
 ---> Using cache
 ---> 64d9f21b9115
Step 14/14 : LABEL com.docker.compose.image.builder=classic
 ---> Using cache
 ---> a121377319a8
Successfully built a121377319a8
Successfully tagged local/reports-frontend:1.0.0
[+] up 22/22
 ✔ Image local/airflow-custom:2.9.3   Built                                                                                                                                                                                             0.1s
 ✔ Image local/reports:1.0.0          Built                                                                                                                                                                                             0.0s
 ✔ Image local/reports-bff:1.0.0      Built                                                                                                                                                                                             0.0s
 ✔ Image local/reports-frontend:1.0.0 Built                                                                                                                                                                                             0.1s
 ✔ Volume job5bff_telemetry_data      Created                                                                                                                                                                                           0.0s
 ✔ Volume job5bff_airflow_db          Created                                                                                                                                                                                           0.0s
 ✔ Volume job5bff_crm_data            Created                                                                                                                                                                                           0.0s
 ✔ Volume job5bff_clickhouse_data     Created                                                                                                                                                                                           0.0s
 ✔ Network job5bff_default            Created                                                                                                                                                                                           0.1s
 ✔ Volume job5bff_keycloak_db         Created                                                                                                                                                                                           0.0s
 ✔ Container postgres-keycloak        Started                                                                                                                                                                                           1.2s
 ✔ Container postgres-telemetry       Started                                                                                                                                                                                           1.7s
 ✔ Container clickhouse               Healthy                                                                                                                                                                                           6.5s
 ✔ Container postgres-airflow         Healthy                                                                                                                                                                                           6.0s
 ✔ Container postgres-crm             Started                                                                                                                                                                                           0.7s
 ✔ Container keycloak                 Started                                                                                                                                                                                           1.4s
 ✔ Container airflow-init             Exited                                                                                                                                                                                           20.7s
 ✔ Container reports                  Started                                                                                                                                                                                           6.6s
 ✔ Container airflow-webserver        Started                                                                                                                                                                                          21.1s
 ✔ Container airflow-scheduler        Started                                                                                                                                                                                          20.8s
 ✔ Container bff                      Started                                                                                                                                                                                           6.8s
 ✔ Container frontend                 Started                                                                                                                                                                                           7.1s

==> Ожидание завершения airflow-init...
==> airflow-init OK
==> Ожидание готовности Airflow Web UI...
==> Ожидание готовности BFF...
==> Ожидание готовности Reports API...

==========================================================================
 Стек успешно запущен:
   Frontend              : http://localhost:3000
   BFF (для фронта)      : http://localhost:8000
   Reports API (debug)   : http://localhost:8001/reports
   Airflow UI            : http://localhost:8080   (admin / admin)
   Keycloak              : http://localhost:8081   (admin / admin)
   ClickHouse HTTP       : http://localhost:8123   (default, без пароля)
   Postgres CRM          : localhost:5433          (crm_user / crm_pass / crm)
   Postgres Telemetry    : localhost:5434          (telemetry_user / telemetry_pass / telemetry)
==========================================================================

NAME                 IMAGE                               COMMAND                  SERVICE              CREATED          STATUS                    PORTS
airflow-scheduler    local/airflow-custom:2.9.3          "/usr/bin/dumb-init …"   airflow-scheduler    52 seconds ago   Up 31 seconds             8080/tcp
airflow-webserver    local/airflow-custom:2.9.3          "/usr/bin/dumb-init …"   airflow-webserver    52 seconds ago   Up 30 seconds (healthy)   0.0.0.0:8080->8080/tcp, [::]:8080->8080/tcp
bff                  local/reports-bff:1.0.0             "docker-entrypoint.s…"   bff                  52 seconds ago   Up 45 seconds             0.0.0.0:8000->8000/tcp, [::]:8000->8000/tcp
clickhouse           clickhouse/clickhouse-server:24.3   "/entrypoint.sh"         clickhouse           52 seconds ago   Up 51 seconds (healthy)   0.0.0.0:8123->8123/tcp, [::]:8123->8123/tcp, 0.0.0.0:9000->9000/tcp, [::]:9000->9000/tcp, 9009/tcp
frontend             local/reports-frontend:1.0.0        "/docker-entrypoint.…"   frontend             52 seconds ago   Up 44 seconds             80/tcp, 0.0.0.0:3000->3000/tcp, [::]:3000->3000/tcp
keycloak             quay.io/keycloak/keycloak:21.1      "/opt/keycloak/bin/k…"   keycloak             52 seconds ago   Up 50 seconds             8443/tcp, 0.0.0.0:8081->8080/tcp, [::]:8081->8080/tcp
postgres-airflow     postgres:16                         "docker-entrypoint.s…"   postgres-airflow     52 seconds ago   Up 51 seconds (healthy)   5432/tcp
postgres-crm         postgres:16                         "docker-entrypoint.s…"   postgres-crm         52 seconds ago   Up 51 seconds (healthy)   0.0.0.0:5433->5432/tcp, [::]:5433->5432/tcp
postgres-keycloak    postgres:14                         "docker-entrypoint.s…"   postgres-keycloak    52 seconds ago   Up 50 seconds (healthy)   5432/tcp
postgres-telemetry   postgres:16                         "docker-entrypoint.s…"   postgres-telemetry   52 seconds ago   Up 50 seconds (healthy)   0.0.0.0:5434->5432/tcp, [::]:5434->5432/tcp
reports              local/reports:1.0.0                 "uvicorn app.main:ap…"   reports              52 seconds ago   Up 45 seconds             0.0.0.0:8001->8000/tcp, [::]:8001->8000/tcp

 Полный сброс: docker compose down -v && ./start.sh
sshuser@astra18zsa-350:~/Desktop/practicum/Sprint9/Task2/Job5BFF$ ./test_bff.sh
1. Проверка, что cookie сессии BFF имеет флаг HttpOnly...
  PASS  Set-Cookie содержит HttpOnly
2. /auth/me без сессии → 401 и без токенов в теле...
  PASS  /auth/me → 401
  PASS  в /auth/me нет токенов
3. /api/reports без сессии → 401...
  PASS  /api/reports без сессии → 401
4. CORS не разрешает произвольный origin...
  PASS  CORS не разрешает чужой origin
5. Во фронтенд-исходниках нет хранилищ токенов...
  PASS  во фронте нет хранения токенов

PASS  Все проверки BFF пройдены.
sshuser@astra18zsa-350:~/Desktop/practicum/Sprint9/Task2/Job5BFF$ python3 test_reports.py
INFO  API_URL = http://localhost:8001
INFO  KEYCLOAK_URL = http://localhost:8081  realm = reports-realm

=== 1. Health-check Reports API ===
  PASS  GET /health -> 200
  PASS  status == ok

=== 2. Получение токенов Keycloak ===
  PASS  token user_1
  PASS  token user_2
  PASS  token admin1

=== 3. /reports без токена → 401 ===
  PASS  GET /reports (no auth) -> 401

=== 4. /reports с невалидным токеном → 401 ===
  PASS  GET /reports (invalid) -> 401

=== 5. /reports с токеном user_1 → 200 + свой username ===
  PASS  GET /reports (user_1) -> 200
  PASS  username == user_1
  PASS  available == True

=== 6. /reports?user_id=<own> → 200 ===
  PASS  GET /reports?user_id=<own> -> 200

=== 7. /reports?user_id=<чужой> → 403 ===
  PASS  GET /reports?user_id=<foreign> -> 403

=== 8. /reports/users (user_1) → 403; (admin1) → 200 ===
  PASS  /reports/users (user_1) -> 403
  PASS  /reports/users (admin1) -> 200
  PASS  count > 0

=== 9. Пустой период → available=false + message ===
  PASS  GET /reports?from=1970-01-01&to=1970-01-02 -> 200
  PASS  available == False
  PASS  message содержит «Данные за указанный период недоступны»
  PASS  period.from корректен

=== 10. Некорректный формат даты → 422 ===
  PASS  GET /reports?from=not-a-date -> 422

=== 11. Только from (без to) → 200 ===
  PASS  GET /reports?from=2020-01-01 -> 200
  PASS  ответ содержит available (bool)

PASS  Все проверки пройдены успешно.

```

 </details>