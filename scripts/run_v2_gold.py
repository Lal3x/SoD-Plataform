"""Publish GOLD001 from frozen runtime snapshots only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pyspark.sql import functions as F

from sod_platform.bronze.ingestion.spark import create_spark_session

ROOT = Path(__file__).resolve().parents[1]
TABLE = "sod.gold.sod_assessment_gold001"
KEY = ["grant_id", "assessment_date"]
FORBIDDEN = {"scenario", "cenario", "classificacao_esperada", "ground_truth", "expected_class", "offline_label"}


def snapshot(spark, table):
    return str(spark.sql(f"SELECT snapshot_id FROM {table}.snapshots ORDER BY committed_at DESC LIMIT 1").first()[0])


def freeze(name):
    return json.loads((ROOT / "artifacts" / "freezes" / name).read_text())


def main():
    risk = freeze("v2-risk-runtime-freeze.json")
    policy = freeze("v2-policy-pd002-1.0.1-runtime-freeze.json")
    evidence = freeze("v2-evidence-1.3.1-runtime-freeze.json")
    ea = freeze("v2-expected-access-runtime-freeze.json")
    assert risk["freeze"] == "V2 RISK RISK001 1.0.0 FROZEN"
    assert policy["freeze"] == "V2 POLICY PD002 1.0.1 FROZEN"
    assert evidence["freeze"] == "V2 EVIDENCE ENGINE EV001 1.3.1 FROZEN"
    assert ea["freeze"] == "V2 EXPECTED ACCESS FROZEN"
    tables = {"risk": risk["output_table"], "policy": policy["output_table"],
              "evidence": evidence["output_tables"]["summary"],
              "expected_access": "sod.access_intelligence.expected_access",
              "context": "sod.silver.access_context"}
    expected_snapshots = {"risk": risk["output_snapshot"], "policy": policy["output_snapshot"],
                          "evidence": evidence["output_snapshots"]["summary"],
                          "expected_access": ea["output_snapshot"],
                          "context": risk["input_snapshots"]["access_context"]}
    spark = create_spark_session(ROOT, "sod-v2-gold001")
    try:
        for name, table in tables.items():
            assert snapshot(spark, table) == expected_snapshots[name], name
        existing = spark.catalog.tableExists(TABLE)
        c, e, p, r, a = (spark.table(tables[n]) for n in ("context", "evidence", "policy", "risk", "expected_access"))
        for name, frame in (("context", c), ("evidence", e), ("policy", p), ("risk", r), ("expected_access", a)):
            assert frame.count() == 75577, name
            assert frame.select("grant_id").distinct().count() == 75577, name
            assert not FORBIDDEN.intersection(frame.columns), name
        gold = (r.alias("r")
            .join(p.alias("p"), KEY)
            .join(e.alias("e"), KEY)
            .join(a.alias("a"), KEY)
            .join(c.alias("c"), KEY)
            .select(
                F.col("r.grant_id"), F.col("r.assessment_date"), F.col("r.identidade_id"),
                F.col("c.comunidade").alias("identity_community"), F.col("c.squad"), F.col("c.cargo"),
                F.col("c.tipo_identidade").alias("identity_type"), F.col("c.status_identidade").alias("identity_status"),
                F.col("c.gestor").alias("manager"), F.col("r.entitlement_id"), F.col("c.sigla_id"),
                F.col("c.comunidade_dona_sigla").alias("owner_community"), F.col("e.community_relation"),
                F.col("c.sigla_publica"), F.col("c.birthright"), F.col("p.trusted_birthright"),
                F.col("c.tipo_atribuicao"), F.col("c.data_concessao"), F.col("c.ultimo_uso"),
                F.col("c.application_owner"), F.col("r.criticidade"), F.col("r.classificacao_dado"),
                F.col("r.privileged"), F.col("r.regulatory_scope"),
                F.col("a.expected_access_status").alias("expected_access_state"),
                F.col("a.expectation_evidence_strength").alias("expected_access_strength"),
                F.col("a.expected_access_reason").alias("expected_access_reason_code"),
                F.col("a.selected_baseline_level"), F.col("a.population_size"),
                F.col("a.support_count"), F.col("a.prevalence"),
                F.lit(None).cast("boolean").alias("baseline_reliable"),
                F.col("e.approval_evidence_status"), F.col("e.approval_linkage_quality").alias("approval_match_strength"),
                F.col("e.approval_candidate_count"), F.col("e.certification_status"),
                F.col("e.data_quality_blocking"), F.col("e.usage_coverage").alias("usage_status"),
                F.col("e.inherited_access_candidate").alias("grant_temporal_status"),
                F.col("p.policy_decision"), F.col("p.policy_rule_id"), F.col("p.policy_reason_code"),
                F.col("p.decision_confidence"), F.col("r.risk_score"), F.col("r.risk_band"),
                F.col("r.priority_action"), F.col("r.risk_driver_1"), F.col("r.risk_driver_2"), F.col("r.risk_driver_3"),
                F.lit("V2").alias("dataset_version"), F.lit("1.0.0").alias("gold_version"),
                F.lit(ea["hts_versions"][0]).alias("hts_version"),
                F.lit(ea["baseline_version"]).alias("baseline_version"),
                F.lit(f'{ea["ea_method_id"]}/{ea["ea_rule_version"]}').alias("expected_access_version"),
                F.lit("EV001/1.3.1").alias("evidence_version"), F.col("p.policy_version"),
                F.col("r.risk_version"), F.col("c.source_snapshot_id").alias("access_context_version"),
                F.current_timestamp().alias("processing_timestamp"))
            .withColumn("review_required", F.col("policy_decision") == "REVISAO")
            .withColumn("remediation_candidate", F.col("policy_decision") == "INDEVIDO")
            .withColumn("operational_queue", F.when((F.col("policy_decision") == "INDEVIDO") & (F.col("risk_band") == "CRITICAL"), "CRITICAL_REMEDIATION")
                .when(F.col("policy_decision") == "INDEVIDO", "REMEDIATION")
                .when((F.col("policy_decision") == "REVISAO") & (F.col("risk_band") == "CRITICAL"), "CRITICAL_REVIEW")
                .when(F.col("policy_decision") == "REVISAO", "REVIEW").otherwise("MONITOR")))
        assert gold.count() == gold.select("grant_id").distinct().count() == 75577
        assert not FORBIDDEN.intersection(gold.columns)
        spark.sql("CREATE NAMESPACE IF NOT EXISTS sod.gold")
        # Replace the stage output on retry; upstream snapshots are validated above.
        if existing:
            gold.writeTo(TABLE).overwrite(F.lit(True))
        else:
            gold.writeTo(TABLE).using("iceberg").create()
        actual = spark.table(TABLE)
        assert actual.count() == actual.select("grant_id").distinct().count() == 75577
        assert [(f.name, f.dataType.simpleString()) for f in actual.schema] == [
            (f.name, f.dataType.simpleString()) for f in gold.schema]
        checks = {
            "policy_mismatch": (p, ["policy_decision", "policy_rule_id", "policy_reason_code", "decision_confidence", "policy_version"]),
            "risk_mismatch": (r, ["risk_score", "risk_band", "priority_action", "risk_driver_1", "risk_driver_2", "risk_driver_3", "risk_version"]),
            "ea_mismatch": (a, ["expected_access_status", "expectation_evidence_strength", "expected_access_reason", "selected_baseline_level", "population_size", "support_count", "prevalence"]),
            "evidence_mismatch": (e, ["approval_evidence_status", "approval_linkage_quality", "approval_candidate_count", "certification_status", "data_quality_blocking", "explicit_anchor_flag"]),
        }
        aliases = {"expected_access_status": "expected_access_state", "expectation_evidence_strength": "expected_access_strength", "expected_access_reason": "expected_access_reason_code", "approval_linkage_quality": "approval_match_strength", "explicit_anchor_flag": "trusted_birthright"}
        mismatches = {}
        for label, (source, fields) in checks.items():
            joined = actual.alias("g").join(source.alias("s"), KEY)
            condition = None
            for field in fields:
                equal = F.col(f"g.{aliases.get(field, field)}").eqNullSafe(F.col(f"s.{field}"))
                condition = ~equal if condition is None else condition | ~equal
            mismatches[label] = joined.where(condition).count()
        assert all(value == 0 for value in mismatches.values()), mismatches
        assert not FORBIDDEN.intersection(actual.columns)
        assert actual.where("policy_decision = 'INDEVIDO' AND NOT remediation_candidate").count() == 0
        assert actual.where("policy_decision = 'REVISAO' AND NOT review_required").count() == 0
        assert actual.where("policy_decision IN ('PADRAO','LEGITIMO') AND remediation_candidate").count() == 0
        report = {"freeze": "V2 GOLD GOLD001 1.0.0 FROZEN", "gold_version": "1.0.0", "dataset_version": "V2",
                  "input_tables": tables, "input_snapshots": expected_snapshots, "output_table": TABLE,
                  "output_snapshot": snapshot(spark, TABLE), "row_count": 75577, "distinct_grants": 75577,
                  "reconciliation": mismatches, "ground_truth_leakage": 0,
                  "view_limitation": "Iceberg Hadoop catalog does not support persistent views; SQL definitions are in sql/gold_views.sql",
                  "schema_hash": hashlib.sha256(gold.schema.json().encode()).hexdigest(),
                  "config_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  "policy_version": policy["policy_version"], "risk_version": risk["risk_version"],
                  "evidence_version": evidence["evidence_version"], "expected_access_version": ea["ea_rule_version"]}
        (ROOT / "artifacts/freezes/v2-gold-runtime-freeze.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(report["freeze"])
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
