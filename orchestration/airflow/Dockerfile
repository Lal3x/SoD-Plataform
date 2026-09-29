FROM apache/airflow:3.0.6-python3.12

USER root
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jre-headless && rm -rf /var/lib/apt/lists/*
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
USER airflow
COPY orchestration/airflow/requirements-airflow.txt /requirements-airflow.txt
COPY pyproject.toml README.md /opt/sod-platform/
COPY src /opt/sod-platform/src
COPY orchestration/airflow/entrypoint-sod.sh /entrypoint-sod.sh
ENTRYPOINT ["/entrypoint-sod.sh"]
RUN pip install --no-cache-dir -r /requirements-airflow.txt && pip install --no-cache-dir /opt/sod-platform
