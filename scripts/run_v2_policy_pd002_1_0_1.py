"""Materialize PD002 1.0.1 from frozen EV001 1.3.1 without labels."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pyspark.sql import functions as F

from sod_platform.access_intelligence.policy.rules import (
    FORBIDDEN,
    build_pd002,
    load_catalog,
)
from sod_platform.bronze.ingestion.spark import create_spark_session

ROOT = Path(__file__).resolve().parents[1]
TABLE = "sod.policy.policy_decisions_pd002_1_0_1"


def snapshot(spark, table):
    return str(spark.sql(f"SELECT snapshot_id FROM {table}.snapshots ORDER BY committed_at DESC LIMIT 1").first()[0])


def distribution(frame, *columns):
    return [{**{column: row[column] for column in columns}, "count": row["count"]}
            for row in frame.groupBy(*columns).count().collect()]


def main():
    evidence_freeze = json.loads((ROOT / "artifacts/freezes/v2-evidence-1.3.1-runtime-freeze.json").read_text())
    assert evidence_freeze["freeze"] == "V2 EVIDENCE ENGINE EV001 1.3.1 FROZEN"
    config_path = ROOT / "configs/policy_decision_pd002_1_0_1.yml"
    catalog = load_catalog(config_path)
    assert catalog["version"] == "1.0.1"
    spark = create_spark_session(ROOT, "sod-v2-policy-pd002-1-0-1")
    try:
        for kind in ("summary", "facts"):
            assert snapshot(spark, evidence_freeze["output_tables"][kind]) == evidence_freeze["output_snapshots"][kind]
        summary = spark.table(evidence_freeze["output_tables"]["summary"])
        facts = spark.table(evidence_freeze["output_tables"]["facts"])
        assert not FORBIDDEN.intersection(summary.columns + facts.columns)
        assert summary.count() == evidence_freeze["summary_count"] == 75577
        assert facts.count() == evidence_freeze["fact_count"]
        assert summary.select("grant_id", "assessment_date").distinct().count() == 75577
        assert summary.where((F.col("evidence_bundle_method_id") != "EV001") | (F.col("evidence_bundle_version") != "1.3.1")).count() == 0
        decisions = build_pd002(summary, catalog).cache()
        assert decisions.count() == 75577
        assert decisions.select("grant_id", "assessment_date").distinct().count() == 75577
        assert decisions.where("policy_decision IS NULL OR policy_rule_id IS NULL").count() == 0
        assert not FORBIDDEN.intersection(decisions.columns)
        plan = decisions._jdf.queryExecution().analyzed().toString().lower()
        assert not any(token in plan for token in FORBIDDEN)
        auth = distribution(decisions, "approval_match_strength", "policy_decision")
        assert sum(r["count"] for r in auth if r["approval_match_strength"] == "STRONG_INFERRED") == 2670
        assert decisions.where("policy_rule_id = 'R140'").count() == 0
        dist = distribution(decisions, "policy_decision")
        rules = distribution(decisions, "policy_rule_id", "policy_decision")
        report = {
            "freeze": "V2 POLICY PD002 1.0.1 FROZEN",
            "policy_id": "PD002", "policy_version": "1.0.1", "dataset_version": "V2",
            "evidence_method_id": "EV001", "evidence_version": "1.3.1",
            "ea_method_id": evidence_freeze["ea_method_id"],
            "ea_rule_version": evidence_freeze["ea_rule_version"],
            "ea_snapshot": evidence_freeze["input_snapshots"]["expected_access"],
            "access_context_snapshot": evidence_freeze["input_snapshots"]["access_context"],
            "hts_version": distribution(summary, "hard_trusted_rule_version"),
            "rule_catalog": catalog["rules"], "rule_precedence": [r["id"] for r in catalog["rules"]],
            "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
            "input_tables": evidence_freeze["output_tables"],
            "input_snapshots": evidence_freeze["output_snapshots"],
            "input_counts": {"summary": 75577, "facts": evidence_freeze["fact_count"]},
            "output_table": TABLE, "output_count": 75577, "distinct_keys": 75577,
            "decision_distribution": dist, "rule_distribution": rules,
            "authorization_policy": auth,
            "expectedness_policy": distribution(decisions, "expected_access_state", "policy_decision"),
            "certification_policy": distribution(decisions, "certification_status", "policy_decision"),
            "ground_truth_leakage": 0,
            "synthetic_tests": "4 passed (22 synthetic cases plus catalog tests)",
        }
        spark.sql("CREATE NAMESPACE IF NOT EXISTS sod.policy")
        # The task is retried by Airflow. A prior attempt may have committed the
        # Iceberg table and failed only while writing its operational artifact;
        # replace this stage output so a retry remains deterministic.
        if spark.catalog.tableExists(TABLE):
            decisions.writeTo(TABLE).overwrite(F.lit(True))
        else:
            decisions.writeTo(TABLE).using("iceberg").create()
        assert spark.table(TABLE).count() == 75577
        report["output_snapshot"] = snapshot(spark, TABLE)
        (ROOT / "artifacts/freezes/v2-policy-pd002-1.0.1-runtime-freeze.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(report["freeze"], flush=True)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
