FROM apache/airflow:3.0.6-python3.12

USER root
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jre-headless && rm -rf /var/lib/apt/lists/*
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
COPY orchestration/airflow/requirements-airflow.txt /requirements-airflow.txt
COPY pyproject.toml README.md /opt/sod-platform/
COPY src /opt/sod-platform/src
COPY configs /opt/sod-platform/configs
COPY scripts /opt/sod-platform/scripts
COPY data/raw /opt/sod-platform/data/raw
COPY orchestration/airflow/dags /opt/airflow/dags
COPY orchestration/airflow/entrypoint-sod.sh /entrypoint-sod.sh
RUN mkdir -p /opt/sod-platform/data/warehouse \
    /opt/sod-platform/artifacts/freezes \
    /opt/sod-platform/artifacts/validation \
    /opt/sod-platform/artifacts/diagnostics \
    /opt/sod-platform/logs \
    && chown -R airflow:root /opt/sod-platform /opt/airflow/dags
USER airflow
ENTRYPOINT ["/entrypoint-sod.sh"]
RUN pip install --no-cache-dir -r /requirements-airflow.txt && pip install --no-cache-dir /opt/sod-platform
