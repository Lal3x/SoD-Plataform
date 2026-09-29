"""Validate, materialize and freeze PD002 before any offline labels are read."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sod_platform.access_intelligence.policy.rules import (
    FORBIDDEN,
    build_pd002,
    load_catalog,
)
from sod_platform.bronze.ingestion.spark import create_spark_session

ROOT = Path(__file__).resolve().parents[1]
TABLE = "sod.policy.policy_decisions_pd002"


def snapshot(spark, table):
    return str(spark.sql(f"SELECT snapshot_id FROM {table}.snapshots ORDER BY committed_at DESC LIMIT 1").first()[0])


def distribution(frame, *columns):
    return [{**{column: row[column] for column in columns}, "count": row["count"]}
            for row in frame.groupBy(*columns).count().collect()]


def main():
    evidence_freeze = json.loads((ROOT / "artifacts/freezes/v2-evidence-1.3.1-runtime-freeze.json").read_text())
    assert evidence_freeze["freeze"] == "V2 EVIDENCE ENGINE EV001 1.3.1 FROZEN"
    config_path = ROOT / "configs/policy_decision_pd002.yml"
    catalog = load_catalog(config_path)
    spark = create_spark_session(ROOT, "sod-v2-policy-pd002")
    try:
        inputs = evidence_freeze["output_tables"]
        for kind in ("summary", "facts"):
            assert snapshot(spark, inputs[kind]) == evidence_freeze["output_snapshots"][kind]
        summary = spark.table(inputs["summary"])
        facts = spark.table(inputs["facts"])
        assert not FORBIDDEN.intersection(summary.columns) and not FORBIDDEN.intersection(facts.columns)
        decisions = build_pd002(summary, catalog).cache()
        count = decisions.count()
        assert count == evidence_freeze["summary_count"] == 75577
        assert decisions.select("grant_id", "assessment_date").distinct().count() == count
        assert decisions.where("policy_decision IS NULL OR policy_rule_id IS NULL").count() == 0
        assert not FORBIDDEN.intersection(decisions.columns)
        plan = decisions._jdf.queryExecution().analyzed().toString().lower()
        assert not any(token in plan for token in FORBIDDEN)
        dist = distribution(decisions, "policy_decision")
        rules = distribution(decisions, "policy_rule_id", "policy_decision")
        automated = sum(r["count"] for r in dist if r["policy_decision"] != "REVISAO")
        report = {
            "freeze": "V2 POLICY DECISION FROZEN", "policy_id": "PD002", "policy_version": "1.0.0",
            "dataset_version": "V2", "evidence_method_id": "EV001", "evidence_version": "1.3.1",
            "ea_method_id": evidence_freeze["ea_method_id"], "ea_rule_version": evidence_freeze["ea_rule_version"],
            "hts_version": distribution(summary, "hard_trusted_rule_version"),
            "rule_catalog": catalog["rules"], "rule_precedence": [r["id"] for r in catalog["rules"]],
            "source_coverage_contract": catalog["request_source_coverage"],
            "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
            "input_snapshots": evidence_freeze["output_snapshots"],
            "output_table": TABLE, "output_count": count, "distinct_keys": count,
            "decision_distribution": dist, "rule_distribution": rules,
            "automation_rate": automated / count, "review_rate": 1 - automated / count,
            "expectedness_policy": distribution(decisions, "expected_access_state", "policy_decision"),
            "authorization_policy": distribution(decisions, "approval_match_strength", "policy_decision"),
            "certification_policy": distribution(decisions, "certification_status", "policy_decision"),
            "ground_truth_leakage": 0,
        }
        spark.sql("CREATE NAMESPACE IF NOT EXISTS sod.policy")
        decisions.writeTo(TABLE).using("iceberg").createOrReplace()
        report["output_snapshot"] = snapshot(spark, TABLE)
        (ROOT / "artifacts/freezes/v2-policy-runtime-freeze.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(report["freeze"], flush=True)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
