"""Materialize only V2 Expected Access and freeze runtime evidence."""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

from pyspark.sql import functions as F

from sod_platform.access_intelligence.expected_access.engine import (
    build_expected_access,
    load_expected_access_config,
)
from sod_platform.access_intelligence.pipeline import _write_snapshot
from sod_platform.bronze.ingestion.spark import create_spark_session
from sod_platform.common.env import load_project_env

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_COLUMNS = {
    "cenario",
    "classificacao_esperada",
    "ground_truth",
    "expected_class",
}
INPUTS = {
    "access_context": "sod.silver.access_context",
    "hard_trusted_set": "sod.access_intelligence.hard_trusted_set",
    "observed_baseline": "sod.access_intelligence.observed_baseline",
    "hierarchical_fallback": "sod.access_intelligence.hierarchical_fallback",
}
OUTPUT = "sod.access_intelligence.expected_access"


def snapshot(spark, table):
    return str(
        spark.sql(
            f"SELECT snapshot_id FROM {table}.snapshots ORDER BY committed_at DESC LIMIT 1"
        ).first()[0]
    )


def counts(frame, *columns):
    return [
        {**{column: row[column] for column in columns}, "count": row["count"]}
        for row in frame.groupBy(*columns).count().collect()
    ]


def quantiles(frame, column):
    values = frame.where(F.col(column).isNotNull()).approxQuantile(
        column, [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0], 0.001
    )
    return dict(zip(("min", "p10", "p25", "median", "p75", "p90", "max"), values))


def main():
    load_project_env(ROOT)
    spark = create_spark_session(ROOT, "sod-v2-expected-access-only")
    try:
        frozen = json.loads(
            (
                ROOT
                / "artifacts/freezes/v2-observed-baseline-fallback-runtime-freeze.json"
            ).read_text()
        )
        assert frozen["freeze"] == "V2 OBSERVED BASELINE + FALLBACK FROZEN"
        input_snapshots = {
            name: snapshot(spark, table) for name, table in INPUTS.items()
        }
        assert input_snapshots == {
            **frozen["input_snapshots"],
            **frozen["output_snapshots"],
        }, "Upstream V2 snapshots changed after freeze"
        frames = {name: spark.table(table) for name, table in INPUTS.items()}
        for name, frame in frames.items():
            assert not FORBIDDEN_COLUMNS.intersection(frame.columns), name
        assert frames["access_context"].count() == 75577
        assert frames["hard_trusted_set"].count() == 75577
        assert frames["hierarchical_fallback"].count() == 75577
        config_path = ROOT / "configs/access_intelligence.yml"
        config = load_expected_access_config(config_path)
        # Search only the runtime rule source and its analyzed Spark plan. The
        # validation script is deliberately outside this runtime path.
        import sod_platform.access_intelligence.expected_access.engine as ea_module

        runtime_source = inspect.getsource(ea_module).lower()
        assert not any(token in runtime_source for token in FORBIDDEN_COLUMNS)
        result = build_expected_access(
            frames["hard_trusted_set"], frames["hierarchical_fallback"], config
        ).cache()
        plan = result._jdf.queryExecution().analyzed().toString().lower()
        assert not any(token in plan for token in FORBIDDEN_COLUMNS)
        assert not FORBIDDEN_COLUMNS.intersection(result.columns)
        rows = result.count()
        distinct = result.select("grant_id").distinct().count()
        missing = (
            frames["access_context"]
            .select("grant_id")
            .join(result.select("grant_id"), "grant_id", "left_anti")
            .count()
        )
        extra = (
            result.select("grant_id")
            .join(frames["access_context"].select("grant_id"), "grant_id", "left_anti")
            .count()
        )
        assert (rows, distinct, missing, extra) == (75577, 75577, 0, 0)
        distribution = counts(result, "expected_access_status")
        reason_distribution = counts(result, "expected_access_reason")
        strength_distribution = counts(result, "expectation_evidence_strength")
        level_distribution = counts(
            result, "selected_baseline_level", "expected_access_status"
        )
        anchor_expected = result.where(
            "expected_access_reason = 'EXPECTED_EXPLICIT_BIRTHRIGHT'"
        ).count()
        baseline_expected = result.where(
            "expected_access_reason = 'EXPECTED_HIGH_CONTEXT_PREVALENCE'"
        ).count()
        assert (
            anchor_expected
            == frames["hard_trusted_set"].where("hard_trusted_flag").count()
            == 12886
        )
        assert (
            result.where(
                "explicit_anchor_flag AND expected_access_status <> 'EXPECTED'"
            ).count()
            == 0
        )
        assert (
            result.where(
                "expected_access_status = 'EXPECTED' AND expected_access_reason NOT IN ('EXPECTED_EXPLICIT_BIRTHRIGHT','EXPECTED_HIGH_CONTEXT_PREVALENCE')"
            ).count()
            == 0
        )
        insufficient = result.where("expected_access_status = 'INSUFFICIENT_EVIDENCE'")
        report = {
            "freeze": "V2 EXPECTED ACCESS FROZEN",
            "dataset_version": "V2",
            "input_snapshots": input_snapshots,
            "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
            "ea_method_id": config.method_id,
            "ea_rule_version": config.version,
            "hts_versions": [
                r[0]
                for r in frames["hard_trusted_set"]
                .select("hard_trusted_rule_version")
                .distinct()
                .collect()
            ],
            "baseline_version": config.supported_baseline_version,
            "fallback_version": config.supported_fallback_version,
            "expected_threshold": config.expected_prevalence_threshold,
            "unexpected_threshold": config.unexpected_prevalence_threshold,
            "assessment_dates": [
                str(r[0]) for r in result.select("assessment_date").distinct().collect()
            ],
            "total_grants": rows,
            "distinct_grants": distinct,
            "missing_grants": missing,
            "extra_grants": extra,
            "status_distribution": distribution,
            "reason_distribution": reason_distribution,
            "strength_distribution": strength_distribution,
            "level_status_distribution": level_distribution,
            "expected_by_trusted_birthright": anchor_expected,
            "expected_by_observed_baseline": baseline_expected,
            "unexpected_prevalence": quantiles(
                result.where("expected_access_status = 'UNEXPECTED'"), "prevalence"
            ),
            "insufficient_reason_distribution": counts(
                insufficient, "expected_access_reason"
            ),
            "ground_truth_leakage": 0,
            "not_executed": [
                "PEER_DISCOVERY",
                "LDA",
                "FP_GROWTH",
                "LEIDEN",
                "NMF_HDBSCAN",
                "EVIDENCE",
                "POLICY",
                "GOLD",
            ],
        }
        _write_snapshot(result, OUTPUT)
        report["output_snapshot"] = snapshot(spark, OUTPUT)
        output = ROOT / "artifacts/freezes/v2-expected-access-runtime-freeze.json"
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(report["freeze"], output, flush=True)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
