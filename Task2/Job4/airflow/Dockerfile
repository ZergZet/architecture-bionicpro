FROM apache/airflow:2.9.3-python3.11

ARG AIRFLOW_UID=50000

USER root

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN if [ "${AIRFLOW_UID}" != "50000" ]; then \
      usermod -u "${AIRFLOW_UID}" airflow && \
      chown -R "${AIRFLOW_UID}:0" /home/airflow /opt/airflow 2>/dev/null || true; \
    fi

USER airflow

RUN pip install --no-cache-dir \
        --retries 10 --timeout 60 \
        clickhouse-connect \
        psycopg2-binary