"""RISK001 configuration, bands and deterministic Spark prioritization."""

import os
import shutil
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest
from pyspark.sql import functions as F

from sod_platform.access_intelligence.risk.engine import (
    band_for_score,
    build_risk_assessment,
    load_risk_config,
)
from sod_platform.bronze.ingestion.spark import create_spark_session

CONFIG = Path(__file__).resolve().parents[3] / "configs/risk.yml"


@pytest.fixture(scope="module")
def spark(tmp_path_factory):
    if shutil.which("java") is None:
        pytest.skip("Spark tests require Java")
    previous = os.environ.get("SOD_WAREHOUSE")
    os.environ["SOD_WAREHOUSE"] = str(tmp_path_factory.mktemp("risk-warehouse"))
    try:
        session = create_spark_session(Path.cwd(), "sod-risk-unit-tests")
        yield session
        session.stop()
    finally:
        if previous is None:
            os.environ.pop("SOD_WAREHOUSE", None)
        else:
            os.environ["SOD_WAREHOUSE"] = previous


def test_config_and_band_boundaries():
    config = load_risk_config(CONFIG)
    assert [
        band_for_score(score, config) for score in (19, 20, 39, 40, 69, 70, 100)
    ] == ["LOW", "MEDIUM", "MEDIUM", "HIGH", "HIGH", "CRITICAL", "CRITICAL"]
    with pytest.raises(ValueError, match="OUT_OF_RANGE"):
        band_for_score(101, config)


@pytest.mark.parametrize(
    "change",
    [
        lambda c: c["criticality"].update({"UNKNOWN": 0}),
        lambda c: c["data_classification"].update({"SECRET": 5}),
        lambda c: c["policy"].update({"INDEVIDO": -1}),
        lambda c: c["bands"].update({"MEDIUM": [19, 39]}),
        lambda c: c["bands"].pop("HIGH"),
    ],
)
def test_config_rejects_invalid_domains_weights_and_bands(tmp_path, change):
    import yaml

    config = deepcopy(load_risk_config(CONFIG))
    change(config)
    path = tmp_path / "invalid-risk.yml"
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    with pytest.raises(ValueError, match="RISK001_CONFIG_INVALID"):
        load_risk_config(path)


def _inputs(spark):
    day = date(2025, 2, 1)
    policy_schema = "grant_id string, assessment_date date, policy_decision string, policy_rule_id string, policy_reason_code string, policy_version string"
    evidence_schema = """grant_id string, assessment_date date, identidade_id string, entitlement_id string,
    evidence_bundle_method_id string, evidence_bundle_version string,
    approval_evidence_status string, approval_linkage_quality string,
    certification_status string, data_quality_blocking boolean, contradiction_codes array<string>,
    application_criticality string, entitlement_privileged boolean,
    data_classification string, regulatory_scope string"""
    context_schema = """grant_id string, assessment_date date, criticidade string,
    classificacao_dado string, regulatory_scope string, privileged boolean"""
    cases = [
        (
            "bad-sensitive",
            "INDEVIDO",
            "R030",
            "CRITICAL",
            True,
            "RESTRICTED",
            "BACEN",
            "NOT_FOUND",
            "UNKNOWN",
            "CERTIFICATION_NOT_FOUND",
        ),
        (
            "bad-low",
            "INDEVIDO",
            "R030",
            "LOW",
            False,
            "PUBLIC",
            "NONE",
            "NOT_FOUND",
            "UNKNOWN",
            "CERTIFICATION_NOT_FOUND",
        ),
        (
            "review",
            "REVISAO",
            "R040",
            "HIGH",
            True,
            "CONFIDENTIAL",
            "SOX",
            "UNIQUE_MATCH",
            "STRONG_INFERRED",
            "REVOKE",
        ),
        (
            "standard",
            "PADRAO",
            "R050",
            "CRITICAL",
            True,
            "RESTRICTED",
            "BACEN",
            "NOT_FOUND",
            "UNKNOWN",
            "CERTIFICATION_NOT_FOUND",
        ),
        (
            "legitimate",
            "LEGITIMO",
            "R020",
            "CRITICAL",
            False,
            "CONFIDENTIAL",
            "SOX",
            "UNIQUE_MATCH",
            "STRONG_INFERRED",
            "CERTIFICATION_NOT_FOUND",
        ),
    ]
    policy = spark.createDataFrame(
        [
            (gid, day, decision, rule, rule, "PD002/1.0.1")
            for gid, decision, rule, *_ in cases
        ],
        policy_schema,
    )
    evidence = spark.createDataFrame(
        [
            (
                gid,
                day,
                f"identity-{gid}",
                f"entitlement-{gid}",
                "EV001",
                "1.3.1",
                approval,
                strength,
                cert,
                False,
                [],
                criticality,
                privileged,
                classification,
                regulatory,
            )
            for gid, _, _, criticality, privileged, classification, regulatory, approval, strength, cert in cases
        ],
        evidence_schema,
    )
    context = spark.createDataFrame(
        [
            (gid, day, criticality, classification, regulatory, privileged)
            for gid, _, _, criticality, privileged, classification, regulatory, *_ in cases
        ],
        context_schema,
    )
    return policy, evidence, context


def test_risk_components_policy_separation_no_double_counting_and_determinism(spark):
    config = load_risk_config(CONFIG)
    policy, evidence, context = _inputs(spark)
    first = build_risk_assessment(policy, evidence, context, config)
    rows = {r.grant_id: r for r in first.collect()}
    assert rows["bad-sensitive"].risk_score > rows["bad-low"].risk_score
    assert rows["bad-sensitive"].priority_rank < rows["bad-low"].priority_rank
    assert rows["review"].priority_action == "REVIEW"
    assert rows["review"].risk_score > config["policy"]["REVISAO"]
    assert rows["standard"].policy_decision == "PADRAO"
    assert rows["standard"].priority_action == "MONITOR"
    assert rows["legitimate"].policy_decision == "LEGITIMO"
    assert rows["bad-low"].risk_score == config["policy"]["INDEVIDO"]
    assert rows["bad-low"].evidence_risk_component == 0
    assert rows["bad-low"].risk_driver_1 == "RD001_POLICY_INDEVIDO"
    assert all(
        rows[r.grant_id].policy_decision == r.policy_decision for r in policy.collect()
    )
    again = build_risk_assessment(
        policy.repartition(3), evidence.repartition(2), context.repartition(4), config
    )
    fields = [
        "grant_id",
        "risk_score",
        "risk_band",
        "risk_driver_1",
        "risk_driver_2",
        "risk_driver_3",
        "priority_rank",
    ]
    assert sorted(tuple(r) for r in first.select(*fields).collect()) == sorted(
        tuple(r) for r in again.select(*fields).collect()
    )


@pytest.mark.parametrize(
    "column,value",
    [
        ("application_criticality", "UNKNOWN"),
        ("data_classification", "SECRET"),
        ("application_criticality", None),
    ],
)
def test_unmapped_or_missing_sensitivity_fails_fast(spark, column, value):
    policy, evidence, context = _inputs(spark)
    evidence = evidence.withColumn(column, F.lit(value))
    with pytest.raises(
        ValueError, match="UNMAPPED_RISK_VALUE|CONTEXT_EVIDENCE_MISMATCH"
    ):
        build_risk_assessment(policy, evidence, context, load_risk_config(CONFIG))
