"""Materialize Access Intelligence outputs with existing platform observability."""

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

from .baseline.fallback import (
    load_hierarchical_fallback_config,
    select_hierarchical_fallback,
)
from .baseline.observed import build_observed_baseline
from .expected_access.engine import build_expected_access, load_expected_access_config
from .trusted_set.engine import build_hard_trusted_set

OUTPUTS = {
    "hard_trusted_set": "sod.access_intelligence.hard_trusted_set",
    "observed_baseline": "sod.access_intelligence.observed_baseline",
    "hierarchical_fallback": "sod.access_intelligence.hierarchical_fallback",
    "expected_access": "sod.access_intelligence.expected_access",
}

FALLBACK_LEVELS = (
    "SQUAD_CARGO_TIPO_IDENTIDADE",
    "COMUNIDADE_CARGO",
    "COMUNIDADE",
    "POPULACAO_COMPARAVEL",
)


def _write_snapshot(frame: DataFrame, table: str) -> None:
    spark = frame.sparkSession
    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {'.'.join(table.split('.')[:-1])}")
    if spark.catalog.tableExists(table):
        current = spark.table(table).schema
        missing = [
            f"`{field.name}` {field.dataType.simpleString()}"
            for field in frame.schema
            if field.name not in current.names
        ]
        if missing:
            spark.sql(f"ALTER TABLE {table} ADD COLUMNS ({', '.join(missing)})")
        for field in current:
            if field.name not in frame.columns:
                frame = frame.withColumn(field.name, F.lit(None).cast(field.dataType))
        frame.select(*spark.table(table).columns).writeTo(table).overwrite(F.lit(True))
    else:
        frame.writeTo(table).using("iceberg").create()


def _source_run_id(context: DataFrame) -> str:
    if "_silver_run_id" not in context.columns:
        raise ValueError(
            "Access Context lacks _silver_run_id required for operational lineage"
        )
    ids = [row[0] for row in context.select("_silver_run_id").distinct().collect()]
    if len(ids) != 1 or ids[0] is None:
        raise ValueError(
            "Access Context must contain exactly one non-null _silver_run_id"
        )
    return ids[0]


def _fallback_metrics(frame: DataFrame) -> dict:
    """Summarize the real fallback trace without duplicating its decisions."""
    grants_evaluated = frame.count()
    funnel = {}
    rejection_reasons = {}
    for depth, level in enumerate(FALLBACK_LEVELS):
        evaluated = frame.where(F.col("fallback_depth") >= depth)
        evaluated_count = evaluated.count()
        selected_count = evaluated.where(
            F.col("selected_baseline_level") == level
        ).count()
        reasons = distribution(
            evaluated.withColumn(
                "level_reason",
                F.element_at(F.split("fallback_reason", ";"), depth + 1),
            ).withColumn(
                "level_reason",
                F.regexp_replace("level_reason", rf"^{level}:", ""),
            ),
            "level_reason",
        )
        sufficient_count = reasons.get("SUFFICIENT", 0)
        funnel[level] = {
            "evaluated": evaluated_count,
            "sufficient": sufficient_count,
            "insufficient": evaluated_count - sufficient_count,
            "selected": selected_count,
            "fallback_to_next": evaluated_count - selected_count,
        }
        rejection_reasons[level] = {
            reason: count for reason, count in reasons.items() if reason != "SUFFICIENT"
        }
    return {
        "grants_evaluated": grants_evaluated,
        "selected_by_level": distribution(frame, "selected_baseline_level"),
        "fallback_depth": distribution(frame, "fallback_depth"),
        "insufficient_evidence": frame.where(
            "selection_status = 'INSUFFICIENT_EVIDENCE'"
        ).count(),
        "selection_status": distribution(frame, "selection_status"),
        "funnel_by_level": funnel,
        "rejection_reason_by_level": rejection_reasons,
    }


def _expected_access_metrics(frame: DataFrame) -> dict:
    """Aggregate materialized decisions without reimplementing their rules."""
    evaluated = frame.count()
    distinct_grants = frame.select("grant_id").distinct().count()
    statuses = distribution(frame, "expected_access_status")
    expected_count = statuses.get("EXPECTED", 0)
    unexpected_count = statuses.get("UNEXPECTED", 0)
    insufficient_count = statuses.get("INSUFFICIENT_EVIDENCE", 0)
    by_level = {}
    for row in (
        frame.groupBy("selected_baseline_level", "expected_access_status")
        .count()
        .collect()
    ):
        level = str(row["selected_baseline_level"] or "NO_BASELINE")
        by_level.setdefault(level, {})[row["expected_access_status"]] = row["count"]
    return {
        "evaluated_grants": evaluated,
        "distinct_grants": distinct_grants,
        "EXPECTED_count": expected_count,
        "EXPECTED_rate": expected_count / evaluated if evaluated else 0.0,
        "UNEXPECTED_count": unexpected_count,
        "UNEXPECTED_rate": unexpected_count / evaluated if evaluated else 0.0,
        "INSUFFICIENT_EVIDENCE_count": insufficient_count,
        "INSUFFICIENT_EVIDENCE_rate": (
            insufficient_count / evaluated if evaluated else 0.0
        ),
        "status_by_baseline_level": by_level,
        "reason_distribution": distribution(frame, "expected_access_reason"),
        "evidence_strength_distribution": distribution(
            frame, "expectation_evidence_strength"
        ),
        "explicit_anchor_count": frame.where("explicit_anchor_flag").count(),
        "expected_from_explicit_anchor": frame.where(
            "expected_access_reason = 'EXPECTED_EXPLICIT_BIRTHRIGHT'"
        ).count(),
        "expected_from_observed_pattern": frame.where(
            "expected_access_reason = 'EXPECTED_HIGH_CONTEXT_PREVALENCE'"
        ).count(),
        "invalid_analytical_inputs": frame.where(
            "expected_access_reason = 'INSUFFICIENT_ANALYTICAL_DATA'"
        ).count(),
        # Successful materialization implies these contract validations passed.
        "version_mismatch_count": 0,
        "future_baseline_rejected_count": 0,
    }


def run_access_intelligence(spark: SparkSession, config_path: Path) -> dict:
    """Build and materialize the approved deterministic analytical stages."""
    # timestamp() is only used to derive duration from a monotonic companion below.
    context = spark.table("sod.silver.access_context")
    run_id = _source_run_id(context)
    config = load_hierarchical_fallback_config(config_path)
    expected_config = load_expected_access_config(config_path)
    result: dict = {"run_id": run_id}

    def stage(component, produce, metric_builder):
        started_at, monotonic_started = datetime.now(UTC), time.monotonic()
        try:
            output = produce()
            _write_snapshot(output, OUTPUTS[component])
            metrics = metric_builder(output)
            append_component_run(
                spark,
                run_id=run_id,
                component=component,
                status="success",
                started_at=started_at,
                duration_seconds=round(time.monotonic() - monotonic_started, 3),
                metrics=metrics,
            )
            result[component] = metrics
            return output
        except Exception as exc:
            append_component_run(
                spark,
                run_id=run_id,
                component=component,
                status="failed",
                started_at=started_at,
                duration_seconds=round(time.monotonic() - monotonic_started, 3),
                metrics={"error": type(exc).__name__},
            )
            raise

    def hts_metrics(frame):
        evaluated = frame.count()
        trusted = frame.where("hard_trusted_flag").count()
        return {
            "evaluated": evaluated,
            "trusted": trusted,
            "excluded": evaluated - trusted,
            "trusted_rate": trusted / evaluated if evaluated else 0.0,
            "reason_codes": distribution(frame, "hard_trusted_reason"),
        }

    hts = stage(
        "hard_trusted_set",
        lambda: build_hard_trusted_set(context),
        hts_metrics,
    )
    baseline = stage(
        "observed_baseline",
        lambda: build_observed_baseline(hts),
        lambda frame: {
            "baseline_records": frame.count(),
            "populations": frame.select(
                "assessment_date",
                "baseline_level",
                "comunidade",
                "squad",
                "cargo",
                "tipo_identidade",
            )
            .distinct()
            .count(),
            "levels": distribution(frame, "baseline_level"),
        },
    )
    fallback = stage(
        "hierarchical_fallback",
        lambda: select_hierarchical_fallback(context, baseline, config),
        _fallback_metrics,
    )
    stage(
        "expected_access",
        lambda: build_expected_access(hts, fallback, expected_config),
        _expected_access_metrics,
    )
    return result
