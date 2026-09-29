# Airflow local — prova de fogo V2

Single-container, SQLite-only local POC: `airflow standalone`, no Celery, Redis, Postgres or provider packages. Airflow invokes project jobs only.

```bash
cp orchestration/airflow/.env.example orchestration/airflow/.env
docker compose -f orchestration/airflow/docker-compose.yml up --build
```

Trigger `sod_runtime_v2` with a safe `lote` and `data_ingestao` (`YYYY-MM-DD`). This is one complete V2 seven-source bundle, so partial bases are intentionally not exposed. Trigger `sod_validation_v2` only after runtime; it is separate because it reads offline ground truth.

Before the proof use `SOD_ENV=local python scripts/reset_local_poc_state.py --dry-run`, inspect the generated inventory, then repeat with `--execute`.
