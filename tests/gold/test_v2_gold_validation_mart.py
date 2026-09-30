"""Gold and offline-mart contract checks with explicit, small test data."""

import json
from pathlib import Path

from pyspark.sql import functions as F

ROOT = Path(__file__).resolve().parents[2]


def _write_table(spark, name: str, rows: list[dict]) -> None:
    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {'.'.join(name.split('.')[:2])}")
    spark.createDataFrame(rows).writeTo(name).using("iceberg").createOrReplace()


def _prepare_mart(spark) -> None:
    gold = json.loads((ROOT / "tests/fixtures/gold/minimal_runtime.json").read_text())
    evaluation = json.loads(
        (ROOT / "tests/fixtures/validation/minimal_policy_evaluation.json").read_text()
    )
    _write_table(spark, "sod.gold.sod_assessment_gold001", gold)
    _write_table(spark, "sod.validation.policy_evaluation", evaluation)
    labeled = [row for row in evaluation if row["ground_truth_class"] is not None]
    _write_table(spark, "sod.validation.confusion_matrix", [{"count": len(labeled)}])
    _write_table(spark, "sod.validation.class_metrics", [{"support": len(labeled)}])
    _write_table(spark, "sod.validation.scenario_metrics", [{"total": len(labeled)}])
    _write_table(
        spark,
        "sod.validation.executive_metrics",
        [{"runtime_grants": 3, "labeled_grants": 2, "unlabeled_grants": 1}],
    )


def test_gold_grain_boundaries_and_queues(spark):
    _prepare_mart(spark)
    gold = spark.table("sod.gold.sod_assessment_gold001")
    assert gold.count() == gold.select("grant_id").distinct().count() == 3
    assert not {
        "cenario",
        "scenario",
        "classificacao_esperada",
        "ground_truth_class",
    } & set(gold.columns)
    assert (
        gold.where("policy_decision = 'INDEVIDO' AND NOT remediation_candidate").count()
        == 0
    )
    assert (
        gold.where("policy_decision = 'REVISAO' AND NOT review_required").count() == 0
    )
    assert (
        gold.where(
            "policy_decision IN ('PADRAO','LEGITIMO') AND remediation_candidate"
        ).count()
        == 0
    )


def test_offline_population_and_metrics(spark):
    _prepare_mart(spark)
    evaluation = spark.table("sod.validation.policy_evaluation")
    labeled = evaluation.where("ground_truth_class IS NOT NULL")
    metrics = spark.table("sod.validation.executive_metrics").first()
    assert (
        evaluation.count(),
        labeled.count(),
        evaluation.where("ground_truth_class IS NULL").count(),
    ) == (3, 2, 1)
    assert metrics.runtime_grants == metrics.labeled_grants + metrics.unlabeled_grants
    assert (
        spark.table("sod.validation.confusion_matrix").agg(F.sum("count")).first()[0]
        == 2
    )
    assert (
        spark.table("sod.validation.class_metrics").agg(F.sum("support")).first()[0]
        == 2
    )
    assert evaluation.where("is_automated OR is_review").count() == 3
    assert (
        spark.table("sod.validation.scenario_metrics").agg(F.sum("total")).first()[0]
        == 2
    )


def test_runtime_has_no_validation_dependency():
    runtime = [ROOT / "scripts/runtime/run_v2_gold.py"] + list(
        (ROOT / "src/sod_platform").rglob("*.py")
    )
    for path in runtime:
        source = path.read_text()
        assert "sod.validation" not in source
        if path.name == "run_v2_gold.py":
            assert "gabarito.csv" not in source
