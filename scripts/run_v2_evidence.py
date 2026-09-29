"""Materialize and freeze the versioned EV001 1.3.1 runtime contract."""

from __future__ import annotations

import hashlib
import inspect
import json
from datetime import UTC, datetime
from pathlib import Path

from sod_platform.access_intelligence.evidence.contract import (
    load_evidence_engine_config,
)
from sod_platform.access_intelligence.evidence.engine import build_evidence
from sod_platform.access_intelligence.evidence.pipeline import _write_snapshot
from sod_platform.bronze.ingestion.spark import create_spark_session
from sod_platform.common.env import load_project_env

ROOT = Path(__file__).resolve().parents[1]
INPUTS = {
    "access_context": "sod.silver.access_context",
    "expected_access": "sod.access_intelligence.expected_access",
    "requests": "sod.silver.iga_access_requests",
    "certifications": "sod.silver.access_certifications",
}
OUTPUTS = {
    "facts": "sod.evidence.evidence_facts_ev001_1_3_1",
    "summary": "sod.evidence.evidence_summary_ev001_1_3_1",
}
FORBIDDEN = {"cenario", "classificacao_esperada", "ground_truth", "expected_class"}


def snapshot(spark, table):
    return str(
        spark.sql(
            f"SELECT snapshot_id FROM {table}.snapshots ORDER BY committed_at DESC LIMIT 1"
        ).first()[0]
    )


def distribution(frame, *columns):
    return [
        {**{column: row[column] for column in columns}, "count": row["count"]}
        for row in frame.groupBy(*columns).count().collect()
    ]


def main():
    load_project_env(ROOT)
    spark = create_spark_session(ROOT, "sod-v2-evidence-only")
    try:
        ea_freeze = json.loads(
            (
                ROOT / "artifacts/freezes/v2-expected-access-runtime-freeze.json"
            ).read_text()
        )
        assert ea_freeze["freeze"] == "V2 EXPECTED ACCESS FROZEN"
        inputs = {name: spark.table(table) for name, table in INPUTS.items()}
        snapshots = {name: snapshot(spark, table) for name, table in INPUTS.items()}
        assert (
            snapshots["access_context"]
            == ea_freeze["input_snapshots"]["access_context"]
        )
        assert snapshots["expected_access"] == ea_freeze["output_snapshot"]
        assert all(
            not FORBIDDEN.intersection(frame.columns) for frame in inputs.values()
        )
        import sod_platform.access_intelligence.evidence.engine as runtime

        assert not any(
            token in inspect.getsource(runtime).lower() for token in FORBIDDEN
        )
        # Runtime must be reproducible from its materialized inputs; historical
        # freeze artifacts are validation evidence, not runtime prerequisites.
        config_path = ROOT / "configs/evidence_engine.yml"
        config = load_evidence_engine_config(config_path)
        assert config.version == "1.3.1"
        outputs = build_evidence(
            inputs["access_context"],
            inputs["expected_access"],
            config,
            evaluated_at=datetime.now(UTC),
            requests=inputs["requests"],
            request_source_coverage="AUTHORITATIVE_FOR_V2",
        )
        summary, facts = outputs.summary.cache(), outputs.facts.cache()
        summary_count, fact_count = summary.count(), facts.count()
        assert summary_count == 75577
        assert summary.select("grant_id").distinct().count() == summary_count
        assert (
            summary.select("grant_id", "assessment_date").distinct().count()
            == summary_count
        )
        assert (
            facts.join(
                summary.select("grant_id", "assessment_date"),
                ["grant_id", "assessment_date"],
                "left_anti",
            ).count()
            == 0
        )
        assert facts.select("evidence_id").distinct().count() == fact_count
        assert (
            summary.where("approval_linkage_quality IN ('DIRECT','CONFIRMED')").count()
            == 0
        )
        for frame in (summary, facts):
            assert not FORBIDDEN.intersection(frame.columns)
            plan = frame._jdf.queryExecution().analyzed().toString().lower()
            assert not any(token in plan for token in FORBIDDEN)
        certification_coverage = summary.where(
            "certification_status IS NOT NULL"
        ).count()
        certification_not_found = facts.where(
            "evidence_type = 'CERTIFICATION_NOT_FOUND'"
        ).count()
        assert certification_coverage == summary_count
        assert (
            certification_not_found
            == summary.where("certification_status = 'CERTIFICATION_NOT_FOUND'").count()
        )
        certification_states = facts.where(
            "evidence_type IN ('CERTIFICATION_DECISION', 'CERTIFICATION_PENDING', 'CERTIFICATION_NOT_FOUND')"
        )
        assert (
            certification_states.groupBy("grant_id", "assessment_date")
            .count()
            .where("count <> 1")
            .count()
            == 0
        )
        approval_distribution = distribution(
            summary, "approval_evidence_status", "approval_linkage_quality"
        )
        expected_distribution = distribution(summary, "expected_access_status")
        assert sorted(
            expected_distribution, key=lambda row: row["expected_access_status"]
        ) == sorted(
            [
                {"expected_access_status": "EXPECTED", "count": 72575},
                {"expected_access_status": "UNEXPECTED", "count": 674},
                {"expected_access_status": "INSUFFICIENT_EVIDENCE", "count": 2328},
            ],
            key=lambda row: row["expected_access_status"],
        )
        per_grant = facts.groupBy("grant_id").count()
        report = {
            "runtime_validation": "EV001 1.3.1 RUNTIME VALIDATED",
            "freeze": "V2 EVIDENCE ENGINE EV001 1.3.1 FROZEN",
            "dataset_version": "V2",
            "evidence_method_id": config.method_id,
            "evidence_version": config.version,
            "ea_method_id": ea_freeze["ea_method_id"],
            "ea_rule_version": ea_freeze["ea_rule_version"],
            "input_snapshots": snapshots,
            "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
            "matching_rules": "same identity and entitlement; APPROVED; request <= approval <= grant <= assessment; exactly one coherent candidate and no conflicting candidate",
            "source_coverage_contract": "AUTHORITATIVE_FOR_V2",
            "summary_count": summary_count,
            "fact_count": fact_count,
            "certification_state_coverage": certification_coverage,
            "certification_not_found_count": certification_not_found,
            "certification_distribution": distribution(summary, "certification_status"),
            "orphan_facts": 0,
            "ground_truth_leakage": 0,
            "facts_per_grant": dict(
                zip(
                    ("min", "p10", "median", "p90", "max"),
                    per_grant.approxQuantile("count", [0.0, 0.1, 0.5, 0.9, 1.0], 0.001),
                )
            ),
            "authorization_distribution": approval_distribution,
            "expected_access_distribution": expected_distribution,
            "expectedness_certification": distribution(
                summary, "expected_access_status", "certification_status"
            ),
            "approval_certification": distribution(
                summary, "approval_evidence_status", "certification_status"
            ),
            "expectedness_authorization": distribution(
                summary, "expected_access_status", "approval_evidence_status"
            ),
            "strong_inferred_context": distribution(
                summary.where("approval_linkage_quality = 'STRONG_INFERRED'"),
                "community_relation",
                "public_application",
                "expected_access_status",
            ),
            "cross_nonpublic_authorization": distribution(
                summary.where("cross_community AND NOT public_application"),
                "approval_evidence_status",
            ),
            "hts_revoke": distribution(
                summary.where(
                    "birthright AND NOT explicit_anchor_flag AND certification_decision = 'REVOKE'"
                ),
                "expected_access_status",
                "approval_evidence_status",
                "certification_decision",
            ),
            "public_nonbirthright": summary.where(
                "public_application AND NOT birthright"
            ).count(),
        }
        _write_snapshot(facts, OUTPUTS["facts"])
        _write_snapshot(summary, OUTPUTS["summary"])
        report["output_snapshots"] = {
            "facts": snapshot(spark, OUTPUTS["facts"]),
            "summary": snapshot(spark, OUTPUTS["summary"]),
        }
        report["output_tables"] = OUTPUTS
        output = ROOT / "artifacts/freezes/v2-evidence-1.3.1-runtime-freeze.json"
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(report["freeze"], output, flush=True)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
