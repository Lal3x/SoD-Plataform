"""Materialize and validate only the V2 Access Context and Hard Trusted Set."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

from pyspark.sql import functions as F

from sod_platform.access_intelligence.context.engine import build_access_context
from sod_platform.access_intelligence.pipeline import _write_snapshot as write_hts
from sod_platform.access_intelligence.trusted_set.engine import build_hard_trusted_set
from sod_platform.bronze.ingestion.spark import create_spark_session
from sod_platform.common.env import load_project_env
from sod_platform.silver.pipeline import _write_snapshot as write_context

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    "identity_master",
    "identity_directory",
    "application_catalog",
    "iga_entitlements",
    "iga_access_assignments",
    "iga_access_requests",
    "access_certifications",
)
PROHIBITED = {"cenario", "classificacao_esperada", "expected_class", "ground_truth"}


def distribution(frame, *columns):
    return {
        "|".join(str(row[c]) for c in columns): row["count"]
        for row in frame.groupBy(*columns).count().collect()
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--assessment-date", type=date.fromisoformat, default=date(2025, 2, 1)
    )
    args = parser.parse_args()
    load_project_env(ROOT)
    spark = create_spark_session(ROOT, "sod-v2-context-hts")
    try:
        tables = {name: spark.table(f"sod.silver.{name}") for name in SOURCES}
        silver = tables["iga_access_assignments"]
        silver_count = silver.count()
        run_ids = [r[0] for r in silver.select("_silver_run_id").distinct().collect()]
        if len(run_ids) != 1 or run_ids[0] is None:
            raise ValueError("Silver assignments need one non-null run ID")
        source_snapshots = {
            name: str(
                spark.sql(
                    f"SELECT snapshot_id FROM sod.silver.{name}.snapshots ORDER BY committed_at DESC LIMIT 1"
                ).first()[0]
            )
            for name in SOURCES
        }
        config_hash = hashlib.sha256(
            (ROOT / "configs/data_quality.yml").read_bytes()
        ).hexdigest()
        context = build_access_context(tables, args.assessment_date).cache()
        context_count = context.count()
        distinct = context.select("grant_id").distinct().count()
        missing = (
            silver.select("grant_id")
            .join(context.select("grant_id"), "grant_id", "left_anti")
            .count()
        )
        extra = (
            context.select("grant_id")
            .join(silver.select("grant_id"), "grant_id", "left_anti")
            .count()
        )
        nulls = {
            c: context.where(F.col(c).isNull()).count()
            for c in (
                "grant_id",
                "identidade_id",
                "entitlement_id",
                "comunidade",
                "comunidade_dona_sigla",
                "birthright",
                "sigla_publica",
            )
        }
        leakage = sorted(PROHIBITED.intersection(context.columns))
        if (
            (silver_count, context_count, distinct) != (75577, 75577, 75577)
            or missing
            or extra
            or leakage
            or any(nulls.values())
        ):
            raise ValueError(
                f"Access Context validation failed: {silver_count=}, {context_count=}, {distinct=}, {missing=}, {extra=}, {nulls=}, {leakage=}"
            )
        report = {
            "silver_run_id": run_ids[0],
            "silver_snapshots": source_snapshots,
            "config_sha256": config_hash,
            "silver_grants": silver_count,
            "access_context_rows": context_count,
            "distinct_grant_ids": distinct,
            "silver_grants_missing_from_context": missing,
            "extra_context_grants": extra,
            "essential_nulls": nulls,
            "leakage_columns": leakage,
            "community_relation": distribution(
                context.withColumn(
                    "community_relation",
                    F.when(F.col("cross_community"), "CROSS_COMMUNITY").otherwise(
                        "SAME_COMMUNITY"
                    ),
                ),
                "community_relation",
            ),
            "community_public": distribution(
                context, "cross_community", "sigla_publica"
            ),
            "birthright": distribution(context, "birthright"),
            "identity_type": distribution(context, "tipo_identidade"),
            "privileged": distribution(context, "privileged"),
            "usage_recorded": distribution(
                context.withColumn("usage_recorded", F.col("ultimo_uso").isNotNull()),
                "usage_recorded",
            ),
            "grant_before_current_community": distribution(
                context, "inherited_access_candidate"
            ),
            "approval_relevance": distribution(context, "approval_relevance"),
            "certification_decision": distribution(context, "certification_decisao"),
        }
        write_context(
            context.withColumn("_silver_run_id", F.lit(run_ids[0])),
            "sod.silver.access_context",
        )
        report["access_context_snapshot"] = str(
            spark.sql(
                "SELECT snapshot_id FROM sod.silver.access_context.snapshots ORDER BY committed_at DESC LIMIT 1"
            ).first()[0]
        )
        print(
            "ACCESS_CONTEXT_V2_VALIDATED",
            json.dumps(
                {
                    k: report[k]
                    for k in (
                        "access_context_snapshot",
                        "access_context_rows",
                        "distinct_grant_ids",
                        "config_sha256",
                    )
                }
            ),
            flush=True,
        )
        hts = build_hard_trusted_set(context).cache()
        hts_count = hts.count()
        hts_distinct = hts.select("grant_id").distinct().count()
        hts_leakage = sorted(PROHIBITED.intersection(hts.columns))
        if hts_count != context_count or hts_distinct != context_count or hts_leakage:
            raise ValueError(
                f"HTS validation failed: {hts_count=}, {hts_distinct=}, {hts_leakage=}"
            )
        report["hts_rows"] = hts_count
        report["hts_distinct_grants"] = hts_distinct
        report["hts_reasons"] = distribution(hts, "hard_trusted_reason")
        report["hts_birthright_public"] = distribution(
            hts.where("birthright"), "sigla_publica", "hard_trusted_reason"
        )
        report["hts_leakage_columns"] = hts_leakage
        report["hts_rule_version"] = distribution(hts, "hard_trusted_rule_version")
        write_hts(hts, "sod.access_intelligence.hard_trusted_set")
        report["hts_snapshot"] = str(
            spark.sql(
                "SELECT snapshot_id FROM sod.access_intelligence.hard_trusted_set.snapshots ORDER BY committed_at DESC LIMIT 1"
            ).first()[0]
        )
        output = ROOT / "artifacts/validation/v2-access-context-hts-metrics.json"
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps(report, sort_keys=True), flush=True)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
