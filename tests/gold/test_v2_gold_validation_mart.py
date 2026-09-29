"""Contract checks against the frozen V2 Gold and offline mart."""

import os
from pathlib import Path

import pytest
from pyspark.sql import functions as F

from sod_platform.bronze.ingestion.spark import create_spark_session

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def spark():
    previous = os.environ.get("SOD_WAREHOUSE")
    os.environ["SOD_WAREHOUSE"] = str(ROOT / "data/warehouse")
    try:
        session = create_spark_session(ROOT, "test-v2-gold-validation")
        try:
            yield session
        finally:
            session.stop()
    finally:
        if previous is None:
            os.environ.pop("SOD_WAREHOUSE", None)
        else:
            os.environ["SOD_WAREHOUSE"] = previous


def test_gold_grain_boundaries_and_queues(spark):
    gold = spark.table("sod.gold.sod_assessment_gold001")
    assert gold.count() == gold.select("grant_id").distinct().count() == 75577
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
    assert (
        gold.where(
            "risk_band = 'CRITICAL' AND policy_decision = 'PADRAO' AND remediation_candidate"
        ).count()
        == 0
    )


def test_offline_population_and_metrics(spark):
    evaluation = spark.table("sod.validation.policy_evaluation")
    labeled = evaluation.where("ground_truth_class IS NOT NULL")
    metrics = spark.table("sod.validation.executive_metrics").first()
    assert evaluation.count() == 75577
    assert labeled.count() == 75485
    assert evaluation.where("ground_truth_class IS NULL").count() == 92
    assert metrics.runtime_grants == metrics.labeled_grants + metrics.unlabeled_grants
    assert (
        spark.table("sod.validation.confusion_matrix").agg(F.sum("count")).first()[0]
        == 75485
    )
    assert (
        spark.table("sod.validation.class_metrics").agg(F.sum("support")).first()[0]
        == 75485
    )
    assert evaluation.where("is_automated OR is_review").count() == 75577
    assert (
        metrics.critical_false_safe_count
        == labeled.where(
            "ground_truth_class = 'INDEVIDO' AND policy_decision IN ('PADRAO','LEGITIMO')"
        ).count()
    )
    assert (
        metrics.false_indevido_count
        == labeled.where(
            "ground_truth_class IN ('PADRAO','LEGITIMO') AND policy_decision = 'INDEVIDO'"
        ).count()
    )
    assert (
        spark.table("sod.validation.scenario_metrics").agg(F.sum("total")).first()[0]
        == 75485
    )
    comparison = spark.table("sod.validation.v1_v2_comparison")
    assert (
        comparison.where(
            "comparison_type IS NULL OR v1_rate IS NULL OR v2_rate IS NULL"
        ).count()
        == 0
    )
    assert (
        spark.table("sod.validation.pipeline_evolution")
        .where("metric IN ('RISK_LOW','RISK_MEDIUM','RISK_HIGH','RISK_CRITICAL')")
        .agg(F.sum("value"))
        .first()[0]
        == 75577
    )


def test_runtime_has_no_validation_dependency():
    runtime = [ROOT / "scripts/run_v2_gold.py"] + list(
        (ROOT / "src/sod_platform").rglob("*.py")
    )
    for path in runtime:
        source = path.read_text()
        assert "sod.validation" not in source
        if path.name == "run_v2_gold.py":
            assert "gabarito.csv" not in source
