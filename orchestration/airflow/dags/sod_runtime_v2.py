"""V2-only runtime orchestration; transformations remain project jobs."""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.models.param import Param
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.utils.task_group import TaskGroup
from helpers import validate_runtime_params

DEFAULT = {"retries": 3, "retry_delay": timedelta(minutes=2)}
with DAG("sod_runtime_v2", start_date=datetime(2026, 1, 1), schedule=None, catchup=False,
         max_active_runs=1, max_active_tasks=1, default_args=DEFAULT,
         params={"lote": Param("carga_2026_09_28", type="string", pattern="^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"),
                 "data_ingestao": Param("2025-02-01", type="string", format="date")},
         tags=["sod", "v2", "runtime"]) as dag:
    validate = PythonOperator(task_id="validar_parametros_e_fontes", python_callable=validate_runtime_params,
                              op_kwargs={"lote": "{{ params.lote }}", "data_ingestao": "{{ params.data_ingestao }}"})
    def job(task_id, command):
        return BashOperator(task_id=task_id, bash_command=f"cd /opt/sod-platform && {command}")
    with TaskGroup("PREPARACAO"):
        bronze = job("bronze", "sod-bronze --config configs/sources.yml --base-dir .")
        bronze_gate = job("gate_bronze", "python scripts/gate_v2_runtime.py bronze")
    with TaskGroup("CURADORIA"):
        silver = job("silver", "sod-silver --silver-only --reference-date '{{ params.data_ingestao }}'")
        silver_gate = job("gate_silver", "python scripts/gate_v2_runtime.py silver")
        context = job("access_context_e_hts", "python scripts/run_v2_context_hts.py --assessment-date '{{ params.data_ingestao }}'")
    with TaskGroup("INTELIGENCIA_DE_ACESSO"):
        baseline = job("observed_baseline_e_fallback", "python scripts/run_v2_baseline_fallback.py")
        expected = job("expected_access", "python scripts/run_v2_expected_access.py")
        evidence = job("evidence", "python scripts/run_v2_evidence.py")
    with TaskGroup("DECISAO"):
        policy = job("policy", "python scripts/run_v2_policy_pd002_1_0_1.py")
        risk = job("risk", "python scripts/run_v2_risk.py")
        gold = job("gold", "python scripts/run_v2_gold.py")
        gold_gate = job("gate_gold", "python scripts/gate_v2_runtime.py gold")
        registered = job("registrar_execucao", "python scripts/register_v2_run.py --lote '{{ params.lote }}' --data-ingestao '{{ params.data_ingestao }}' --run-id '{{ run_id }}'")
        trigger_validation = TriggerDagRunOperator(task_id="disparar_validacao_offline", trigger_dag_id="sod_validation_v2", wait_for_completion=False, conf={"runtime_dag_id": "sod_runtime_v2", "runtime_run_id": "{{ run_id }}", "lote": "{{ params.lote }}", "data_ingestao": "{{ params.data_ingestao }}"})
    validate >> bronze >> bronze_gate >> silver >> silver_gate >> context >> baseline >> expected >> evidence >> policy >> risk >> gold >> gold_gate >> registered >> trigger_validation
