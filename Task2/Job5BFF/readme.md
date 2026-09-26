# Reports App: CRM + Telemetry + ClickHouse + Airflow + Keycloak + Reports API + BFF + Frontend

Демонстрационный стек, который показывает безопасную аутентификацию и авторизацию для сервиса отчётов на базе бионических протезов. Фронтенд никогда не видит токены Keycloak: между браузером и IdP стоит BFF (Backend-for-Frontend), реализующий паттерн **«Прокси для токенов»** на **PKCE (S256)**.

---

## Схема взаимодействяи

```
┌──────────────┐  HttpOnly cookie  ┌──────────────┐  client_secret  ┌──────────────┐
│              │  ────────────────>│              │  PKCE (S256)    │              │
│  Frontend    │   /auth/login     │     BFF      │  ─────────────> │   Keycloak   │
│  (React)     │   /api/reports    │  (Express)   │  code exchange  │  (IdP)       │
│              │  <────────────────│              │  <───────────── │              │
└──────────────┘   JSON без токенов└──────┬───────┘  access/refresh └──────────────┘
      :3000                              │                                  :8081
                                         │ Bearer <access_token>
                                         ▼
                                  ┌──────────────┐       ┌──────────────┐
                                  │ Reports API  │──────>│ ClickHouse   │
                                  │  (FastAPI)   │       │   (mart)     │
                                  └──────────────┘       └──────────────┘
                                         ▲                      ▲
                                         │                      │
                                  ┌──────┴───────────┐   ┌──────┴──────┐
                                  │   Airflow DAG    │   │ CRM / Tele- │
                                  │   (каждые 5 мин) │──>│ metry (PG)  │
                                  └──────────────────┘   └─────────────┘
```

- **Frontend** — React SPA. Общается **только** с BFF через `credentials: 'include'`. Ничего не знает о Keycloak и не хранит токенов.
- **BFF** — Express-сервис. Единственный, кто знает `client_secret` и общается с Keycloak. Токены хранит **в серверной сессии**, браузеру отдаёт `HttpOnly`-cookie. Проксирует `/api/*` в Reports API, добавляя `Authorization: Bearer <access_token>`.
- **Keycloak** — IdP с realm `reports-realm`, двумя OIDC-клиентами (`reports-bff`, `reports-cli`) и 51 пользователем.
- **Reports API** — FastAPI-сервис. Проверяет JWT через JWKS Keycloak и читает витрину из ClickHouse.
- **Airflow** — DAG `crm_telemetry_mart` раз в 5 минут пересобирает витрину.
- **ClickHouse** — OLAP-витрина `mart.client_telemetry_analytics`, оптимизирована под запросы по клиенту.
- **PostgreSQL** — три отдельные БД: `crm`, `telemetry`, `airflow` (плюс `keycloak_db`).

---

## Структура проекта

```
Job4_5/
├── docker-compose.yml
├── start.sh
├── test_auth_reports.sh
├── test_reports.py
├── test_bff.sh
├── README.md
├── keycloak/
│   └── realm-export.json
├── bff/
│   ├── Dockerfile
│   ├── package.json
│   └── server.js
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
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
---

## Запуск

### Требования

- Docker 20.10+
- Docker Compose v2 (`docker compose`)
- `curl`, `python3`

### Команды

```bash
chmod +x start.sh test_auth_reports.sh test_bff.sh test_reports.py
docker compose down -v
./start.sh
```

Скрипт `start.sh`:

1. Готовит каталоги `airflow/{logs,plugins,dags}` и правит права (Airflow работает под UID 50000).
2. Собирает и поднимает сервисы.
3. Дожидается завершения `airflow-init` (миграции Airflow DB + создание admin/admin).
4. Ждёт готовности Airflow UI (`:8080`), BFF (`:8000`) и Reports API (`:8001`).

---

## Описание работы

### 1. Вход пользователя

1. Пользователь нажимает **Войти** на фронтенде.
2. Фронт делает редирект на `GET /auth/login` BFF.
3. BFF генерирует `state` и `code_verifier`, считает `code_challenge = S256(verifier)` и редиректит браузер в Keycloak.
4. Пользователь вводит логин/пароль в форме Keycloak.
5. Keycloak редиректит на `GET /auth/callback` BFF с `code` и `state`.
6. BFF проверяет `state`, отправляет `code` + `code_verifier` + `client_secret` в Keycloak, получает `access_token`, `refresh_token`, `id_token`.
7. BFF сохраняет токены **в серверной сессии**, браузеру ставит `HttpOnly`-cookie (`connect.sid`).
8. BFF редиректит браузер обратно на фронтенд (`http://localhost:3000`).

### 2. Работа с API

1. Фронт вызывает `fetch('/api/reports', { credentials: 'include' })`.
2. Браузер автоматически прикрепляет cookie сессии BFF.
3. BFF берёт `access_token` из сессии, при необходимости обновляет через `refresh_token`.
4. BFF проксирует запрос в Reports API, добавляя `Authorization: Bearer <access_token>`.
5. Reports API валидирует JWT, читает данные из ClickHouse и возвращает отчёт.
6. BFF передаёт ответ фронту **без токенов**.

### 3. Защита от XSS и утечек

| Угроза                                     | Как защищаемся                                                  |
| ------------------------------------------ | --------------------------------------------------------------- |
| Кража токенов через `document.cookie`      | Cookie сессии BFF имеет флаг `HttpOnly` — JS её не читает       |
| Кража токенов через `localStorage`         | Токены вообще не попадают на фронт                              |
| Подмена `client_secret`                    | Секрет хранится только на сервере BFF                           |
| Перехват authorization code                | Code бесполезен без `code_verifier` (PKCE S256)                 |
| CSRF с чужого origin                       | CORS разрешает только `http://localhost:3000`, `SameSite=Lax`    |
| Утечка токена через `/auth/me`             | Эндпоинт возвращает только данные пользователя, без токенов     |
| Запрос чужого отчёта                       | Reports API сверяет `client_id` из запроса с `preferred_username` из JWT |

---

<details> <summary> Описание подготовленных данных  </summary>

### CRM (`postgres-crm:5432/crm`)

Таблица `clients`:

- `id`, `full_name`, `email`, `username`
- `prosthesis_type`, `prosthesis_model`, `serial_number`
- `order_number`, `order_price`, `install_date`

**50 записей** (`user_1` … `user_50`), ФИО, модели протезов (`BionicArm X1`, `BionicLeg Pro 3000`, `MyoHand S2`, `NeuroLeg Elite`, `TitanArm M5`), серийники `SN-000001` … `SN-000050`.

### Telemetry (`postgres-telemetry:5432/telemetry`)

Таблица `telemetry`:

- `id`, `serial_number`, `event_type`, `event_time`
- `response_time_ms`, `battery_level`, `signal_quality`, `error_code`

**20 событий на каждый** серийный номер из CRM (итого 1000 записей). Типы событий: `activation`, `movement`, `charging`, `calibration`, `error`, `shutdown`, `firmware_update`.

### Витрина ClickHouse (`clickhouse:8123`, БД `mart`)

- `mart.telemetry_events` — сырые события.
- `mart.client_telemetry_analytics` — денормализованная витрина:
  - ключ `ORDER BY (client_id, serial_number)` для быстрого доступа по клиенту,
  - метрики: `total_events`, `avg_response_time`, `avg_battery_level`, `avg_signal_quality`, `error_events`, `last_event_time`.

DAG `crm_telemetry_mart` собирает витрину **раз в 5 минут** (расписание `*/5 * * * *`).

</details>

---

<details> <summary> Описание сервисов </summary>



## Порты и креды

| Сервис                 | Порт (host) | Адрес / Креды                                              |
| ---------------------- | ----------- | ---------------------------------------------------------- |
| Frontend (React)       | 3000        | http://localhost:3000                                      |
| BFF (для фронта)       | 8000        | http://localhost:8000                                      |
| Reports API (debug)    | 8001        | http://localhost:8001                                      |
| Airflow UI             | 8080        | http://localhost:8080 (`admin` / `admin`)                  |
| Keycloak               | 8081        | http://localhost:8081 (`admin` / `admin`)                  |
| ClickHouse HTTP        | 8123        | `default`, без пароля, БД `mart`                           |
| Postgres CRM           | 5433        | `crm_user` / `crm_pass` / БД `crm`                         |
| Postgres Telemetry     | 5434        | `telemetry_user` / `telemetry_pass` / БД `telemetry`       |
| Postgres Keycloak      | внутренний  | `keycloak_user` / `keycloak_password` / БД `keycloak_db`   |
| Postgres Airflow       | внутренний  | `airflow` / `airflow` / БД `airflow`                       |

---

## Аутентификация и авторизация

Realm: **`reports-realm`**.

### Клиенты Keycloak

| clientId           | Тип            | Назначение                                       | Особенности                               |
| ------------------ | -------------- | ------------------------------------------------ | ----------------------------------------- |
| `reports-bff`      | confidential   | Серверная часть — обмен кода на токены           | PKCE S256, redirect `http://localhost:8000/auth/callback`, secret `bff-secret-change-me` |
| `reports-cli`      | public         | Только для тестов (`password` grant)             | Используется в `test_auth_reports.sh`     |
| `reports-api`      | bearer-only    | Подразумеваемый downstream-API                   | Только для валидации JWT                  |

### Пользователи

- `user_1` … `user_50`, пароль `password123`, роли `user`, `prothetic_user`.
- `admin1`, пароль `admin123`, роль `administrator`.

### Роли

- `user` — обычный пользователь.
- `administrator` — доступ к `/reports/users`.
- `prothetic_user` — пользователь с протезом, может запрашивать отчёты по себе.

---

## Reports API

FastAPI-сервис, порт `8000` внутри docker-сети, `8001` проброшен наружу для отладки.

| Метод | Путь                                              | Доступ                                    |
| ----- | ------------------------------------------------- | ----------------------------------------- |
| GET   | `/health`                                         | без авторизации                           |
| GET   | `/reports`                                        | любой аутентифицированный                 |
| GET   | `/reports?from=YYYY-MM-DD&to=YYYY-MM-DD`          | то же, с фильтром по периоду              |
| GET   | `/reports?user_id=N`                              | только если `N` — это ваш `client_id`     |
| GET   | `/reports/me`                                     | алиас `/reports`                          |
| GET   | `/reports/users`                                  | только роль `administrator`               |

### Валидация токена

- JWT подписывается RS256, публичный ключ берётся из JWKS Keycloak.
- JWKS кэшируется на 5 минут.
- Принимается **любой** из двух issuer’ов: `http://localhost:8081/realms/reports-realm` и `http://keycloak:8080/realms/reports-realm`. Это необходимо, потому что BFF обменивает код по внутреннему URL и получает токен с внутренним `iss`.

### Ответ при отсутствии данных

Когда за указанный период данных нет, API возвращает **HTTP 200**:

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

Фронт показывает жёлтую плашку.

---

## BFF API

Порт `8000` снаружи и внутри.

| Метод | Путь                    | Назначение                                                        |
| ----- | ----------------------- | ----------------------------------------------------------------- |
| GET   | `/health`               | Проверка живости                                                  |
| GET   | `/auth/login`           | Генерит `state` + `code_verifier`, редиректит в Keycloak          |
| GET   | `/auth/callback`        | Обмен кода на токены, сохранение в сессии, редирект на фронт      |
| GET   | `/auth/me`              | Возвращает данные пользователя без токенов                        |
| POST  | `/auth/logout`          | Уничтожает сессию                                                 |
| ALL   | `/api/*`                | Прозрачный прокси в Reports API с `Authorization: Bearer <token>` |

### Сессия

- `express-session` с in-memory store (демо).
- Cookie: `HttpOnly`, `SameSite=Lax`, `maxAge=8h`.
- Токены хранятся в `session.tokens`, данные пользователя — в `session.user`.
- При истечении `access_token` BFF обновляет его через `refresh_token`.

</details>

---


<details> <summary> Тесты </summary>

## Тесты безопасности

`test_bff.sh` проверяет 5 инвариантов, из-за которых XSS не может украсть токены.

```bash
chmod +x test_bff.sh
./test_bff.sh
```

Что проверяется:

1. **HttpOnly-cookie сессии.** JS не может прочитать `document.cookie`.
2. **`/auth/me` не возвращает токенов.** Токены не утекают через API.
3. **`/api/reports` защищён.** Без сессии — `401`.
4. **CORS ограничен доверенным origin.** Сторонний сайт не прочитает ответы.
5. **Фронт не хранит токены в `localStorage`/`sessionStorage`.**

Пример вывода:

```
1. Проверка, что cookie сессии BFF имеет флаг HttpOnly...
УСПЕХ: Set-Cookie содержит HttpOnly
2. /auth/me без сессии → 401 и без токенов в теле...
УСПЕХ: /auth/me → 401
УСПЕХ: в /auth/me нет токенов
3. /api/reports без сессии → 401...
УСПЕХ: /api/reports без сессии → 401
4. CORS не разрешает произвольный origin...
УСПЕХ: CORS не разрешает чужой origin
5. Во фронтенд-исходниках нет хранилищ токенов...
УСПЕХ: во фронте нет хранения токенов
Все проверки BFF пройдены.
```

---

## Описание функциональных тестов

### `test_auth_reports.sh` — проверки Reports API

```bash
./test_auth_reports.sh
```

Покрывает:

- получение токенов через `reports-cli` (password grant) для `user_1`, `user_2`, `admin1`;
- `/reports` без токена → 401;
- `/reports` с невалидным токеном → 401;
- `/reports` с токеном `user_1` → 200, `username=user_1`;
- `/reports?user_id=<own>` → 200;
- `/reports?user_id=<чужой>` → 403;
- `/reports/users` под `user_1` → 403, под `admin1` → 200;
- пустой период (`1970-01-01…1970-01-02`) → 200 + `available=false` + `message="Данные за указанный период недоступны"`;
- некорректный формат даты → 422;
- только `from` без `to` → 200.

### `test_reports.py` — то же на Python

```bash
python3 test_reports.py
```

Идентичный набор проверок, но через `urllib` без внешних зависимостей.

### `test_bff.sh` — защита BFF

См. раздел выше.

По умолчанию тесты ходят в Reports API по `http://localhost:8001`, а в BFF — по `http://localhost:8000`.

</details>
 

---

<details> <summary> Изменение расписания Airflow DAG </summary>

DAG-файл: `airflow/dags/crm_telemetry_mart.py`.

```python
SCHEDULE = "*/5 * * * *"   # каждые 5 минут
```

### Примеры

| Расписание                | Значение          |
| ------------------------- | ----------------- |
| Каждую минуту             | `* * * * *`       |
| Каждые 5 минут            | `*/5 * * * *`     |
| Каждые 15 минут           | `*/15 * * * *`    |
| Каждый час в :00          | `0 * * * *`       |
| Раз в сутки в 02:00 UTC   | `0 2 * * *`       |
| По будням в 09:30 UTC     | `30 9 * * 1-5`    |

### Как применить изменения

1. Отредактируйте `SCHEDULE` в `airflow/dags/crm_telemetry_mart.py`.
2. Airflow сам подхватит изменения DAG’а через ~30 секунд (scheduler периодически сканирует папку `dags`).
3. Проверить в UI: **http://localhost:8080** → DAGs → `crm_telemetry_mart`.
Если DAG уже был запущен с другим расписанием, старое останется в истории, новое начнёт применяться со следующего интервала.

 </details>

---

 <details> <summary> Команды проверки сервисов </summary>

```bash
# Проверить, что Keycloak поднялся
curl -s http://localhost:8081/realms/reports-realm | head

# Проверить BFF
curl -s http://localhost:8000/health
curl -i http://localhost:8000/auth/me                # ожидаем 401
curl -i http://localhost:8000/api/reports            # ожидаем 401

# Проверить Reports API напрямую (debug)
curl -s http://localhost:8001/health
curl -i http://localhost:8001/reports                # ожидаем 401
```

 </details>

---

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

 <details> <summary> Screen тестов </summary>

![TestPassed]( .\screens\testpassed.png )

 </details>

  <details> <summary> Данные не найдены </summary>

![NoData]( .\screens\nodata.png )

 </details>

  <details> <summary> Отчёт по данным </summary>

![Report]( .\screens\report.png )

 </details>