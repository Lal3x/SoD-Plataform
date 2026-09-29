"""Persist EV001 outputs and aggregate observability from materialized facts."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from sod_platform.observability.access_intelligence import (
    append_component_run,
    distribution,
)

from .contract import load_evidence_engine_config
from .engine import build_evidence

OUTPUTS = {
    "evidence_summary": "sod.evidence.evidence_summary",
    "evidence_facts": "sod.evidence.evidence_facts",
}


def _write_snapshot(frame: DataFrame, table: str) -> None:
    spark = frame.sparkSession
    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {'.'.join(table.split('.')[:-1])}")
    # These tables are complete, versioned snapshots. createOrReplace keeps the
    # physical Iceberg schema aligned with an explicit EV contract evolution.
    frame.writeTo(table).using("iceberg").createOrReplace()


def evidence_metrics(summary: DataFrame, facts: DataFrame) -> dict:
    """Aggregate produced outputs without reimplementing evidence semantics."""
    summary_rows = summary.count()
    distinct_grants = summary.select("grant_id").distinct().count()
    distinct_keys = summary.select("grant_id", "assessment_date").distinct().count()
    fact_count = facts.count()
    distinct_evidence_ids = facts.select("evidence_id").distinct().count()
    mixed_codes = summary.select(F.explode("mixed_evidence_codes").alias("code"))
    contradiction_codes = summary.select(
        F.explode("contradiction_codes").alias("code")
    )
    return {
        "evaluated_grants": summary_rows,
        "distinct_grants": distinct_grants,
        "summary_row_count": summary_rows,
        "distinct_summary_keys": distinct_keys,
        "duplicate_summary_keys": summary_rows - distinct_keys,
        "grain_integrity": summary_rows == distinct_keys,
        "evidence_count": fact_count,
        "distinct_evidence_ids": distinct_evidence_ids,
        "duplicate_evidence_ids": fact_count - distinct_evidence_ids,
        "facts_without_bundle_id": facts.where(
            "evidence_bundle_id is null"
        ).count(),
        "evidence_type_distribution": distribution(facts, "evidence_type"),
        "evidence_category_distribution": distribution(facts, "evidence_category"),
        "evidence_reliability_distribution": distribution(
            facts, "evidence_reliability"
        ),
        "approval_relevance_distribution": distribution(
            summary, "approval_relevance"
        ),
        "approval_linkage_quality_distribution": distribution(
            summary, "approval_linkage_quality"
        ),
        "certification_distribution": distribution(
            summary, "certification_decision"
        ),
        "expected_access_distribution": distribution(
            summary, "expected_access_status"
        ),
        "expectation_strength_distribution": distribution(
            summary, "expectation_evidence_strength"
        ),
        "expected_access_reason_distribution": distribution(
            summary, "expected_access_reason"
        ),
        "usage_coverage_distribution": distribution(summary, "usage_coverage"),
        "identity_history_complete_distribution": distribution(
            summary, "identity_history_complete"
        ),
        "cross_community_count": summary.where("cross_community").count(),
        "public_application_count": summary.where("public_application").count(),
        "birthright_count": summary.where("birthright").count(),
        "explicit_anchor_count": summary.where("explicit_anchor_flag").count(),
        "inherited_candidate_count": summary.where(
            "inherited_access_candidate"
        ).count(),
        "no_usage_recorded_count": summary.where("no_usage_recorded").count(),
        "blocking_dq_count": summary.where("data_quality_blocking").count(),
        "mixed_evidence_count": summary.where("mixed_evidence_flag").count(),
        "mixed_evidence_code_distribution": distribution(mixed_codes, "code"),
        "contradictory_evidence_count": summary.where(
            "contradictory_evidence_flag"
        ).count(),
        "contradiction_code_distribution": distribution(
            contradiction_codes, "code"
        ),
        "unknown_reliability_count": facts.where(
            "evidence_reliability = 'UNKNOWN'"
        ).count(),
        # Successful materialization means the temporal input gate passed.
        "future_evidence_rejected_count": 0,
        "evidence_bundle_versions": distribution(
            summary, "evidence_bundle_version"
        ),
        "source_snapshots": summary.select(
            "access_context_source_snapshot_id"
        ).distinct().count(),
        "expected_access_method_versions": distribution(
            summary, "expected_access_method_version"
        ),
        "baseline_versions": distribution(summary, "baseline_version"),
        "fallback_versions": distribution(summary, "fallback_version"),
    }


def run_evidence_engine(spark: SparkSession, config_path: Path) -> dict:
    """Read approved upstream tables and materialize EV001 evidence."""
    started_at, monotonic_started = datetime.now(UTC), time.monotonic()
    context = spark.table("sod.silver.access_context")
    expected = spark.table("sod.access_intelligence.expected_access")
    requests = spark.table("sod.silver.iga_access_requests")
    config = load_evidence_engine_config(config_path)
    run_ids = [row[0] for row in context.select("_silver_run_id").distinct().collect()]
    if len(run_ids) != 1 or run_ids[0] is None:
        raise ValueError("Access Context must contain exactly one non-null _silver_run_id")
    run_id = run_ids[0]
    try:
        outputs = build_evidence(context, expected, config, evaluated_at=started_at,
                                 requests=requests)
        _write_snapshot(outputs.facts, OUTPUTS["evidence_facts"])
        _write_snapshot(outputs.summary, OUTPUTS["evidence_summary"])
        metrics = evidence_metrics(outputs.summary, outputs.facts)
        append_component_run(
            spark,
            run_id=run_id,
            component="evidence_engine",
            status="success",
            started_at=started_at,
            duration_seconds=round(time.monotonic() - monotonic_started, 3),
            metrics=metrics,
        )
        return {"run_id": run_id, "evidence_engine": metrics}
    except Exception as exc:
        append_component_run(
            spark,
            run_id=run_id,
            component="evidence_engine",
            status="failed",
            started_at=started_at,
            duration_seconds=round(time.monotonic() - monotonic_started, 3),
            metrics={"error": type(exc).__name__},
        )
        raise
