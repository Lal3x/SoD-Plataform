"""PD001 snapshot materialization and operational metrics."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession

from sod_platform.observability.access_intelligence import (
    append_component_run,
    distribution,
)

from .contract import load_policy_config
from .engine import build_policy_decisions

OUTPUTS = {"policy_decisions": "sod.policy.policy_decisions"}


def policy_metrics(decisions: DataFrame) -> dict:
    rows = decisions.count()
    keys = decisions.select("grant_id", "assessment_date").distinct().count()
    return {
        "evaluated_grants": rows,
        "distinct_decision_keys": keys,
        "duplicate_decisions": rows - keys,
        "grain_integrity": rows == keys,
        "classification_distribution": distribution(decisions, "classification"),
        "winning_rule_distribution": distribution(decisions, "winning_rule_id"),
        "primary_reason_distribution": distribution(decisions, "primary_reason_code"),
        "source_snapshot_count": decisions.select("source_snapshot_id")
        .distinct()
        .count(),
    }


def run_policy_decision(spark: SparkSession, config_path: Path) -> dict:
    started_at, started = datetime.now(UTC), time.monotonic()
    summary = spark.table("sod.evidence.evidence_summary")
    config = load_policy_config(config_path)
    run_ids = [r[0] for r in summary.select("silver_run_id").distinct().collect()]
    if len(run_ids) != 1 or run_ids[0] is None:
        raise ValueError(
            "Evidence summary must contain exactly one non-null silver_run_id"
        )
    run_id = run_ids[0]
    try:
        outputs = build_policy_decisions(
            summary, config, decision_run_id=run_id, decided_at=started_at
        )
        table = OUTPUTS["policy_decisions"]
        spark.sql("CREATE NAMESPACE IF NOT EXISTS sod.policy")
        outputs.decisions.writeTo(table).using("iceberg").createOrReplace()
        metrics = policy_metrics(outputs.decisions)
        append_component_run(
            spark,
            run_id=run_id,
            component="policy_decision",
            status="success",
            started_at=started_at,
            duration_seconds=round(time.monotonic() - started, 3),
            metrics=metrics,
        )
        return {"run_id": run_id, "policy_decision": metrics}
    except Exception as exc:
        append_component_run(
            spark,
            run_id=run_id,
            component="policy_decision",
            status="failed",
            started_at=started_at,
            duration_seconds=round(time.monotonic() - started, 3),
            metrics={"error": type(exc).__name__},
        )
        raise
