ARG AIRFLOW_VERSION=2.9.3
ARG PYTHON_VERSION=3.11
ARG AIRFLOW_UID=50000

FROM apache/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION}

ARG AIRFLOW_UID=50000
ENV AIRFLOW_UID=${AIRFLOW_UID}

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

USER airflow
RUN pip install --no-cache-dir \
        clickhouse-connect \
        psycopg2-binary