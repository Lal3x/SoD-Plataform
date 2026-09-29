FROM python:3.12-slim
WORKDIR /opt/sod-platform
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . streamlit
COPY apps/streamlit ./apps/streamlit
EXPOSE 8501
CMD ["streamlit", "run", "apps/streamlit/app.py", "--server.address=0.0.0.0", "--server.port=8501"]
