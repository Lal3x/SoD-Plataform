"""Separate offline validation; it is never an upstream of runtime."""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG("sod_validation_v2", start_date=datetime(2026, 1, 1), schedule=None, catchup=False,
         max_active_runs=1, max_active_tasks=1,
         default_args={"retries": 3, "retry_delay": timedelta(minutes=2)},
         tags=["sod", "v2", "validation", "offline"]) as dag:
    validation = BashOperator(task_id="materializar_validation_mart",
                              bash_command="cd /opt/sod-platform && python scripts/run_v2_validation_mart.py")
    descriptive = BashOperator(task_id="metricas_descritivas",
                               bash_command="cd /opt/sod-platform && python scripts/complete_v2_validation_mart.py")
    validation >> descriptive
