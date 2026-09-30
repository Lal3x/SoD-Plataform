# Full local application image for the Streamlit interface.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-21-jre-headless \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
ENV PYTHONPATH=/opt/sod-platform

WORKDIR /opt/sod-platform
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . streamlit
COPY apps/streamlit ./apps/streamlit

EXPOSE 8501
CMD ["streamlit", "run", "apps/streamlit/app.py", "--server.address=0.0.0.0", "--server.port=8501"]
