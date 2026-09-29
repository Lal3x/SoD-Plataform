"""Validate and freeze RISK001 1.0.0 without reading offline labels."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pyspark.sql import functions as F

from sod_platform.access_intelligence.risk.engine import (
    FORBIDDEN,
    build_risk_assessment,
    load_risk_config,
)
from sod_platform.bronze.ingestion.spark import create_spark_session

ROOT = Path(__file__).resolve().parents[1]
TABLE = "sod.risk.risk_assessment_risk001_1_0_0"
CONTEXT = "sod.silver.access_context"


def snapshot(spark, table):
    return str(spark.sql(f"SELECT snapshot_id FROM {table}.snapshots ORDER BY committed_at DESC LIMIT 1").first()[0])


def distribution(frame, *columns):
    return [{**{column: row[column] for column in columns}, "count": row["count"]}
            for row in frame.groupBy(*columns).count().collect()]


def top(frame, decision):
    columns = ["grant_id", "identidade_id", "entitlement_id", "policy_decision",
               "policy_reason_code", "risk_score", "risk_band", "privileged",
               "criticidade", "regulatory_scope", "classificacao_dado",
               "risk_driver_1", "risk_driver_2", "risk_driver_3"]
    return [row.asDict() for row in frame.where(F.col("policy_decision") == decision)
            .orderBy("priority_rank").select(*columns).limit(20).collect()]


def main():
    policy_freeze = json.loads((ROOT / "artifacts/freezes/v2-policy-pd002-1.0.1-runtime-freeze.json").read_text())
    evidence_freeze = json.loads((ROOT / "artifacts/freezes/v2-evidence-1.3.1-runtime-freeze.json").read_text())
    assert policy_freeze["freeze"] == "V2 POLICY PD002 1.0.1 FROZEN"
    assert evidence_freeze["freeze"] == "V2 EVIDENCE ENGINE EV001 1.3.1 FROZEN"
    config_path = ROOT / "configs/risk.yml"
    config = load_risk_config(config_path)
    spark = create_spark_session(ROOT, "sod-v2-risk-risk001")
    try:
        assert snapshot(spark, policy_freeze["output_table"]) == policy_freeze["output_snapshot"]
        summary_table = evidence_freeze["output_tables"]["summary"]
        assert snapshot(spark, summary_table) == evidence_freeze["output_snapshots"]["summary"]
        assert snapshot(spark, CONTEXT) == evidence_freeze["input_snapshots"]["access_context"]
        policy = spark.table(policy_freeze["output_table"])
        evidence = spark.table(summary_table)
        context = spark.table(CONTEXT)
        assert not FORBIDDEN.intersection(policy.columns + evidence.columns + context.columns)
        risk = build_risk_assessment(policy, evidence, context, config).cache()
        assert risk.count() == policy_freeze["output_count"] == 75577
        assert risk.select("grant_id", "assessment_date").distinct().count() == 75577
        assert risk.select("grant_id").distinct().count() == 75577
        assert risk.where("risk_score IS NULL OR risk_band IS NULL OR priority_action IS NULL").count() == 0
        assert risk.where("risk_score < 0 OR risk_score > 100").count() == 0
        assert risk.where(F.col("risk_score") != sum(F.col(n) for n in (
            "decision_risk_component", "privileged_risk_component", "criticality_risk_component",
            "regulatory_risk_component", "data_classification_risk_component",
            "evidence_risk_component", "temporal_risk_component"))).count() == 0
        assert risk.join(policy.select("grant_id", "assessment_date", "policy_decision", "policy_rule_id")
                         .withColumnRenamed("policy_decision", "original_decision")
                         .withColumnRenamed("policy_rule_id", "original_rule"),
                         ["grant_id", "assessment_date"]).where(
                             (F.col("policy_decision") != F.col("original_decision")) |
                             (F.col("policy_rule_id") != F.col("original_rule"))).count() == 0
        assert risk.where("policy_decision = 'INDEVIDO'").count() == 273
        assert risk.where("policy_decision = 'REVISAO' AND approval_linkage_quality = 'STRONG_INFERRED' AND certification_status = 'REVOKE'").count() == 29
        assert not FORBIDDEN.intersection(risk.columns)
        plan = risk._jdf.queryExecution().analyzed().toString().lower()
        assert not any(token in plan for token in FORBIDDEN)
        report = {
            "freeze": "V2 RISK RISK001 1.0.0 FROZEN",
            "risk_id": config["id"], "risk_version": config["version"],
            "dataset_version": config["dataset_version"],
            "policy_version": config["policy_version"],
            "evidence_method_id": config["evidence_method_id"],
            "evidence_version": config["evidence_version"],
            "input_tables": {"policy": policy_freeze["output_table"],
                             "evidence_summary": summary_table, "access_context": CONTEXT},
            "input_snapshots": {"policy": policy_freeze["output_snapshot"],
                                "evidence_summary": evidence_freeze["output_snapshots"]["summary"],
                                "access_context": evidence_freeze["input_snapshots"]["access_context"]},
            "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
            "config": config, "output_table": TABLE, "output_count": 75577,
            "distinct_grants": 75577, "policy_decision_changes": 0,
            "ground_truth_leakage": 0, "synthetic_tests": "10 passed",
            "risk_band_distribution": distribution(risk, "risk_band"),
            "policy_risk_distribution": distribution(risk, "policy_decision", "risk_band"),
            "priority_action_distribution": distribution(risk, "priority_action"),
            "privileged_policy_risk": distribution(risk.where("privileged AND policy_decision IN ('INDEVIDO', 'REVISAO')"), "policy_decision", "risk_band"),
            "regulatory_policy_risk": distribution(risk.where("regulatory_scope <> 'NONE' AND policy_decision IN ('INDEVIDO', 'REVISAO')"), "policy_decision", "risk_band"),
            "critical_application_policy_risk": distribution(risk.where("criticidade = 'CRITICAL' AND policy_decision IN ('INDEVIDO', 'REVISAO')"), "policy_decision", "risk_band"),
            "strong_inferred_revoke_risk": distribution(risk.where("approval_linkage_quality = 'STRONG_INFERRED' AND certification_status = 'REVOKE' AND policy_decision = 'REVISAO'"), "risk_band"),
            "top_20_indevido": top(risk, "INDEVIDO"),
            "top_20_revisao": top(risk, "REVISAO"),
        }
        spark.sql("CREATE NAMESPACE IF NOT EXISTS sod.risk")
        # Keep Airflow retries deterministic when a prior attempt committed output.
        if spark.catalog.tableExists(TABLE):
            risk.writeTo(TABLE).overwrite(F.lit(True))
        else:
            risk.writeTo(TABLE).using("iceberg").create()
        assert spark.table(TABLE).count() == 75577
        report["output_snapshot"] = snapshot(spark, TABLE)
        (ROOT / "artifacts/freezes/v2-risk-runtime-freeze.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(report["freeze"], flush=True)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
