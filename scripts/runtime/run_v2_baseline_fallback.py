"""Freeze V2 observed baseline and fallback before offline label inspection."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pyspark.sql import functions as F

from sod_platform.access_intelligence.baseline.fallback import (
    LEVELS,
    load_hierarchical_fallback_config,
    select_hierarchical_fallback,
)
from sod_platform.access_intelligence.baseline.observed import build_observed_baseline
from sod_platform.access_intelligence.pipeline import _write_snapshot
from sod_platform.bronze.ingestion.spark import create_spark_session
from sod_platform.common.env import load_project_env

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = {"cenario", "classificacao_esperada", "ground_truth", "expected_class"}


def snapshot(spark, name):
    return str(
        spark.sql(
            f"SELECT snapshot_id FROM {name}.snapshots ORDER BY committed_at DESC LIMIT 1"
        ).first()[0]
    )


def quantiles(frame, column):
    values = frame.where(F.col(column).isNotNull()).approxQuantile(
        column, [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 1.0], 0.001
    )
    return dict(
        zip(("min", "p10", "p25", "median", "p75", "p90", "p95", "p99", "max"), values)
    )


def main():
    load_project_env(ROOT)
    spark = create_spark_session(ROOT, "sod-v2-observed-baseline-fallback")
    try:
        context_name = "sod.silver.access_context"
        hts_name = "sod.access_intelligence.hard_trusted_set"
        context = spark.table(context_name).cache()
        hts = spark.table(hts_name)
        assert not FORBIDDEN.intersection(context.columns)
        assert not FORBIDDEN.intersection(hts.columns)
        assert context.count() == 75577 == hts.count()
        assert context.select("grant_id").distinct().count() == 75577
        assert hts.select("grant_id").distinct().count() == 75577
        assert (
            context.select("grant_id")
            .join(hts.select("grant_id"), "grant_id", "left_anti")
            .count()
            == 0
        )
        config_path = ROOT / "configs/access_intelligence.yml"
        config = load_hierarchical_fallback_config(config_path)
        input_snapshots = {
            "access_context": snapshot(spark, context_name),
            "hard_trusted_set": snapshot(spark, hts_name),
        }
        comparable = context.where(
            (~F.col("data_quality_blocking"))
            & (F.lower("status_identidade") == "active")
            & (~F.coalesce(F.col("cross_community"), F.lit(True)))
            & F.col("data_concessao").isNotNull()
            & (F.col("data_concessao") <= F.col("assessment_date"))
        )
        total_ids = context.select("identidade_id").distinct().count()
        comparable_ids = comparable.select("identidade_id").distinct().count()
        baseline = build_observed_baseline(context, config.baseline_version).cache()
        baseline_count = baseline.count()
        assert not FORBIDDEN.intersection(baseline.columns)
        assert (
            baseline.groupBy(
                "assessment_date",
                "baseline_level",
                "comunidade",
                "squad",
                "cargo",
                "tipo_identidade",
                "entitlement_id",
            )
            .count()
            .where("count > 1")
            .count()
            == 0
        )
        fallback = select_hierarchical_fallback(context, baseline, config).cache()
        assert fallback.count() == 75577
        assert fallback.select("grant_id").distinct().count() == 75577
        assert not FORBIDDEN.intersection(fallback.columns)
        runtime = {
            "input_snapshots": input_snapshots,
            "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
            "baseline_version": config.baseline_version,
            "fallback_version": config.version,
            "minimum_population_size": config.minimum_population_size,
            "minimum_support_count": config.minimum_support_count,
            "expected_candidate_threshold_unchanged": 0.80,
            "hierarchy": [level for level, _ in LEVELS],
            "assessment_dates": [
                str(r[0])
                for r in context.select("assessment_date").distinct().collect()
            ],
            "total_grants": 75577,
            "total_identities": total_ids,
            "comparable_identities": comparable_ids,
            "excluded_identities": total_ids - comparable_ids,
            "comparable_grants": comparable.count(),
            "exclusion_reason_grant_counts": {
                "blocking_dq": context.where("data_quality_blocking").count(),
                "non_active": context.where(
                    "lower(status_identidade) <> 'active' OR status_identidade IS NULL"
                ).count(),
                "cross_or_unknown_community": context.where(
                    "cross_community OR cross_community IS NULL"
                ).count(),
                "future_or_missing_grant_date": context.where(
                    "data_concessao IS NULL OR data_concessao > assessment_date"
                ).count(),
            },
            "baseline_rows": baseline_count,
            "baseline_distribution": {},
            "selected_distribution": {},
            "algorithms_not_executed": ["LDA", "FP_GROWTH", "LEIDEN", "NMF_HDBSCAN"],
            "runtime_ground_truth_leakage": 0,
        }
        for level, _ in LEVELS:
            rows = baseline.where(F.col("baseline_level") == level)
            selected = fallback.where(F.col("selected_baseline_level") == level)
            runtime["baseline_distribution"][level] = {
                "rows": rows.count(),
                "population_size": quantiles(rows, "population_size"),
                "support_count": quantiles(rows, "support_count"),
                "prevalence": quantiles(rows, "prevalence"),
            }
            runtime["selected_distribution"][level] = {
                "population_count": rows.select(
                    "comunidade", "squad", "cargo", "tipo_identidade"
                )
                .distinct()
                .count(),
                "grant_count": context.count(),
                "reliable_baseline_count": selected.count(),
                "median_prevalence": quantiles(selected, "selected_prevalence").get(
                    "median"
                ),
                "p90_prevalence": quantiles(selected, "selected_prevalence").get("p90"),
                "high_prevalence_count": selected.where(
                    "selected_prevalence >= 0.80"
                ).count(),
            }
        reliable = fallback.where("baseline_sufficient")
        runtime["reliable_grants"] = reliable.count()
        runtime["insufficient_grants"] = 75577 - runtime["reliable_grants"]
        runtime["high_prevalence_grants"] = {
            str(t): reliable.where(F.col("selected_prevalence") >= t).count()
            for t in (0.80, 0.90, 0.95)
        }
        runtime["selected_prevalence"] = quantiles(reliable, "selected_prevalence")
        # Diagnostic only; does not change the selected baseline or gates.
        comparable_flags = comparable.select("grant_id").withColumn(
            "comparable_holder", F.lit(True)
        )
        comparable_types = (
            comparable.select("identidade_id", "tipo_identidade")
            .distinct()
            .withColumn("comparable_population_member", F.lit(True))
        )
        loo = fallback.join(
            context.select("grant_id", "identidade_id", "tipo_identidade"), "grant_id"
        )
        loo = loo.join(comparable_flags, "grant_id", "left").join(
            comparable_types, ["identidade_id", "tipo_identidade"], "left"
        )
        population_member = F.coalesce(F.col("comparable_holder"), F.lit(False)) | (
            (F.col("selected_baseline_level") == "POPULACAO_COMPARAVEL")
            & F.coalesce(F.col("comparable_population_member"), F.lit(False))
        )
        loo = (
            loo.withColumn(
                "loo_population",
                F.col("selected_population_size") - population_member.cast("int"),
            )
            .withColumn(
                "loo_support",
                F.col("selected_support_count")
                - F.coalesce(F.col("comparable_holder"), F.lit(False)).cast("int"),
            )
            .withColumn(
                "loo_prevalence",
                F.when(
                    F.col("loo_population") > 0,
                    F.col("loo_support") / F.col("loo_population"),
                ),
            )
        )
        runtime["loo_prevalence"] = quantiles(loo, "loo_prevalence")
        runtime["loo_high_prevalence_grants"] = {
            str(t): loo.where(F.col("loo_prevalence") >= t).count()
            for t in (0.80, 0.90, 0.95)
        }
        _write_snapshot(baseline, "sod.access_intelligence.observed_baseline")
        _write_snapshot(fallback, "sod.access_intelligence.hierarchical_fallback")
        runtime["output_snapshots"] = {
            "observed_baseline": snapshot(
                spark, "sod.access_intelligence.observed_baseline"
            ),
            "hierarchical_fallback": snapshot(
                spark, "sod.access_intelligence.hierarchical_fallback"
            ),
        }
        runtime["freeze"] = "V2 OBSERVED BASELINE + FALLBACK FROZEN"
        output = (
            ROOT / "artifacts/freezes/v2-observed-baseline-fallback-runtime-freeze.json"
        )
        output.write_text(
            json.dumps(runtime, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(runtime["freeze"], output, flush=True)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
