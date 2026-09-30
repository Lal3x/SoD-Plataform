"""Offline POC evaluation. This module is never imported by runtime jobs."""

from __future__ import annotations

import json
from pathlib import Path

from pyspark.sql import functions as F

from sod_platform.bronze.ingestion.spark import create_spark_session

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "sod.validation."


def write(frame, name, spark):
    """Materialize a validation result, replacing the prior run atomically."""
    table = PREFIX + name
    frame.writeTo(table).using("iceberg").createOrReplace()


def main():
    freeze = json.loads(
        (ROOT / "artifacts/freezes/v2-gold-runtime-freeze.json").read_text()
    )
    assert freeze["freeze"] == "V2 GOLD GOLD001 1.0.0 FROZEN"
    spark = create_spark_session(ROOT, "sod-v2-validation-offline")
    try:
        gold = spark.table(freeze["output_table"])
        assert (
            str(
                spark.sql(
                    f"SELECT snapshot_id FROM {freeze['output_table']}.snapshots ORDER BY committed_at DESC LIMIT 1"
                ).first()[0]
            )
            == freeze["output_snapshot"]
        )
        gt = spark.read.option("header", True).csv(
            str(ROOT / "tests/fixtures/v2/gabarito.csv")
        )
        assert (
            gt.groupBy("identidade_id", "entitlement_id")
            .count()
            .where("count > 1")
            .count()
            == 0
        )
        evaluation = (
            gold.alias("g")
            .join(gt.alias("t"), ["identidade_id", "entitlement_id"], "left")
            .select(
                "grant_id",
                "identidade_id",
                "entitlement_id",
                "sigla_id",
                "birthright",
                "sigla_publica",
                F.col("t.classificacao_esperada").alias("ground_truth_class"),
                F.col("t.cenario").alias("scenario"),
                "policy_decision",
                "policy_rule_id",
                "risk_score",
                "risk_band",
                "expected_access_state",
                "prevalence",
                "approval_evidence_status",
                "approval_match_strength",
                "certification_status",
            )
            .withColumn(
                "is_correct", F.col("policy_decision") == F.col("ground_truth_class")
            )
            .withColumn(
                "is_automated",
                F.col("policy_decision").isin("PADRAO", "LEGITIMO", "INDEVIDO"),
            )
            .withColumn("is_review", F.col("policy_decision") == "REVISAO")
            .withColumn(
                "critical_false_safe",
                (F.col("ground_truth_class") == "INDEVIDO")
                & F.col("policy_decision").isin("PADRAO", "LEGITIMO"),
            )
            .withColumn(
                "false_indevido",
                F.col("ground_truth_class").isin("PADRAO", "LEGITIMO")
                & (F.col("policy_decision") == "INDEVIDO"),
            )
        )
        assert evaluation.count() == gold.count() == 75577
        assert evaluation.where("ground_truth_class IS NULL").count() == 92
        spark.sql("CREATE NAMESPACE IF NOT EXISTS sod.validation")
        write(evaluation, "policy_evaluation", spark)
        labeled = spark.table(PREFIX + "policy_evaluation").where(
            "ground_truth_class IS NOT NULL"
        )
        labeled.createOrReplaceTempView("v2_labeled")
        spark.table(PREFIX + "policy_evaluation").createOrReplaceTempView("v2_eval")
        write(
            spark.sql(
                """SELECT ground_truth_class AS ground_truth, policy_decision AS predicted_policy,
            COUNT(*) AS count, COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY ground_truth_class) AS rate
            FROM v2_labeled GROUP BY ground_truth_class, policy_decision"""
            ),
            "confusion_matrix",
            spark,
        )
        classes = spark.createDataFrame(
            [("PADRAO",), ("LEGITIMO",), ("INDEVIDO",)], ["class_name"]
        )
        classes.createOrReplaceTempView("v2_classes")
        write(
            spark.sql(
                """SELECT c.class_name,
            SUM(CASE WHEN e.ground_truth_class = c.class_name AND e.policy_decision = c.class_name THEN 1 ELSE 0 END) AS tp,
            SUM(CASE WHEN e.ground_truth_class <> c.class_name AND e.policy_decision = c.class_name THEN 1 ELSE 0 END) AS fp,
            SUM(CASE WHEN e.ground_truth_class = c.class_name AND e.policy_decision <> c.class_name THEN 1 ELSE 0 END) AS fn,
            SUM(CASE WHEN e.ground_truth_class = c.class_name THEN 1 ELSE 0 END) AS support,
            CASE WHEN SUM(CASE WHEN e.policy_decision = c.class_name THEN 1 ELSE 0 END) = 0 THEN NULL ELSE
              SUM(CASE WHEN e.ground_truth_class = c.class_name AND e.policy_decision = c.class_name THEN 1 ELSE 0 END) /
              SUM(CASE WHEN e.policy_decision = c.class_name THEN 1 ELSE 0 END) END AS precision,
            SUM(CASE WHEN e.ground_truth_class = c.class_name AND e.policy_decision = c.class_name THEN 1 ELSE 0 END) /
              SUM(CASE WHEN e.ground_truth_class = c.class_name THEN 1 ELSE 0 END) AS recall
            FROM v2_classes c CROSS JOIN v2_labeled e GROUP BY c.class_name"""
            ).withColumn(
                "f1",
                2
                * F.col("precision")
                * F.col("recall")
                / (F.col("precision") + F.col("recall")),
            ),
            "class_metrics",
            spark,
        )
        write(
            spark.sql("""SELECT scenario, COUNT(*) AS total,
            SUM(CASE WHEN policy_decision = 'PADRAO' THEN 1 ELSE 0 END) AS padrao,
            SUM(CASE WHEN policy_decision = 'LEGITIMO' THEN 1 ELSE 0 END) AS legitimo,
            SUM(CASE WHEN policy_decision = 'INDEVIDO' THEN 1 ELSE 0 END) AS indevido,
            SUM(CASE WHEN policy_decision = 'REVISAO' THEN 1 ELSE 0 END) AS revisao,
            AVG(CAST(is_correct AS DOUBLE)) AS accuracy,
            AVG(CAST(is_automated AS DOUBLE)) AS automation_rate,
            AVG(CAST(is_review AS DOUBLE)) AS review_rate
            FROM v2_labeled GROUP BY scenario"""),
            "scenario_metrics",
            spark,
        )
        metrics = spark.sql("""SELECT COUNT(*) AS runtime_grants,
            COUNT(ground_truth_class) AS labeled_grants,
            COUNT(*) - COUNT(ground_truth_class) AS unlabeled_grants,
            AVG(CASE WHEN ground_truth_class IS NOT NULL THEN CAST(is_correct AS DOUBLE) END) AS overall_exact_accuracy,
            AVG(CASE WHEN ground_truth_class IS NOT NULL AND is_automated THEN CAST(is_correct AS DOUBLE) END) AS automated_decision_accuracy,
            AVG(CAST(is_automated AS DOUBLE)) AS automation_rate,
            AVG(CAST(is_review AS DOUBLE)) AS review_rate,
            SUM(CASE WHEN critical_false_safe THEN 1 ELSE 0 END) AS critical_false_safe_count,
            SUM(CASE WHEN false_indevido THEN 1 ELSE 0 END) AS false_indevido_count,
            SUM(CASE WHEN ground_truth_class = 'INDEVIDO' AND risk_band = 'CRITICAL' THEN 1 ELSE 0 END) /
              SUM(CASE WHEN ground_truth_class = 'INDEVIDO' THEN 1 ELSE 0 END) AS indevido_critical_risk_rate,
            SUM(CASE WHEN scenario = 'normal' AND NOT birthright AND NOT sigla_publica AND prevalence >= 0.90 THEN 1 ELSE 0 END) /
              SUM(CASE WHEN scenario = 'normal' AND NOT birthright AND NOT sigla_publica THEN 1 ELSE 0 END) AS normal_identifiability_90,
            SUM(CASE WHEN ground_truth_class = 'LEGITIMO' AND scenario LIKE '%cross%' AND approval_match_strength = 'STRONG_INFERRED' THEN 1 ELSE 0 END) /
              NULLIF(SUM(CASE WHEN ground_truth_class = 'LEGITIMO' AND scenario LIKE '%cross%' THEN 1 ELSE 0 END), 0) AS cross_legitimo_authorization_coverage
            FROM v2_eval""")
        class_metrics = spark.table(PREFIX + "class_metrics")
        for label in ("PADRAO", "LEGITIMO", "INDEVIDO"):
            row = (
                class_metrics.where(F.col("class_name") == label)
                .select("precision", "recall")
                .first()
            )
            metrics = metrics.withColumn(
                label.lower() + "_precision", F.lit(row["precision"])
            )
            metrics = metrics.withColumn(
                label.lower() + "_recall", F.lit(row["recall"])
            )
        write(metrics, "executive_metrics", spark)
        evolution = [
            ("V1", "EA_EXPECTED", 18721),
            ("V1", "EA_UNEXPECTED", 602),
            ("V1", "EA_INSUFFICIENT", 49507),
        ]
        for status, count in [
            (r[0], r[1])
            for r in gold.groupBy("expected_access_state").count().collect()
        ]:
            evolution.append(("V2", "EA_" + status.replace("_EVIDENCE", ""), count))
        evolution.extend(
            [
                ("V2", "GOLD_ASSESSMENTS", 75577),
                ("V2", "RISK_ASSESSMENTS", 75577),
                ("V2", "SILVER_CANONICAL_GRANTS", 75577),
                ("V2", "EVIDENCE_FACTS", 1889425),
            ]
        )
        write(
            spark.createDataFrame(evolution, ["dataset_version", "metric", "value"]),
            "pipeline_evolution",
            spark,
        )
        comparisons = [
            ("EA_EXPECTED", 18721, 72575, "DESCRIPTIVE_ONLY"),
            ("EA_UNEXPECTED", 602, 674, "DESCRIPTIVE_ONLY"),
            ("EA_INSUFFICIENT", 49507, 2328, "DESCRIPTIVE_ONLY"),
        ]
        write(
            spark.createDataFrame(
                comparisons, ["metric", "v1_count", "v2_count", "comparison_type"]
            ),
            "v1_v2_comparison",
            spark,
        )
        result = metrics.first().asDict()
        assert (
            result["labeled_grants"] + result["unlabeled_grants"]
            == result["runtime_grants"]
        )
        assert (
            spark.table(PREFIX + "confusion_matrix").agg(F.sum("count")).first()[0]
            == result["labeled_grants"]
        )
        assert (
            class_metrics.agg(F.sum("support")).first()[0] == result["labeled_grants"]
        )
        (ROOT / "artifacts/validation/v2-validation-mart-metrics.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n"
        )
        print("V2 VALIDATION MART MATERIALIZED", result, flush=True)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
