"""PD001 rule, precedence, temporal and grain contracts."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pyspark.sql import functions as F

from sod_platform.access_intelligence.policy.contract import load_policy_config
from sod_platform.access_intelligence.policy.engine import build_policy_decisions

ASSESSED = date(2025, 2, 1)
EVALUATED = datetime(2025, 2, 1, 12, tzinfo=UTC)


def _summary(spark):
    schema = """grant_id string, assessment_date date, evidence_bundle_id string,
    evidence_bundle_method_id string, evidence_bundle_version string,
    evidence_ids array<string>, access_context_source_snapshot_id string,
    data_quality_blocking boolean, explicit_anchor_flag boolean,
    expected_access_status string, expectation_evidence_strength string,
    approval_relevance string, approval_linkage_quality string, approval_effective_at date,
    certification_decision string, certification_date date, certification_campaign_id string,
    public_application boolean, certification_pending_count long,
    inherited_access_candidate boolean, identity_history_complete boolean,
    no_usage_recorded boolean, usage_coverage string, contradiction_codes array<string>"""
    rows = [
        (
            "A",
            ASSESSED,
            "bundle-a",
            "EV001",
            "1.1.0",
            ["a1"],
            "snapshot-a",
            False,
            True,
            "EXPECTED",
            "HIGH",
            "NOT_FOUND",
            None,
            None,
            "REVOKE",
            date(2025, 1, 10),
            "C1",
            False,
            0,
            False,
            True,
            True,
            "UNKNOWN",
            [],
        ),
        (
            "B",
            ASSESSED,
            "bundle-b",
            "EV001",
            "1.1.0",
            ["b1"],
            "snapshot-b",
            False,
            False,
            "UNEXPECTED",
            "LOW",
            "NOT_FOUND",
            None,
            None,
            None,
            None,
            None,
            False,
            0,
            False,
            True,
            False,
            "COMPLETE",
            [],
        ),
        (
            "C",
            ASSESSED,
            "bundle-c",
            "EV001",
            "1.1.0",
            ["c1"],
            "snapshot-c",
            False,
            False,
            "INSUFFICIENT_EVIDENCE",
            None,
            "UNCERTAIN",
            "STRONG_INFERRED",
            date(2024, 7, 1),
            None,
            None,
            None,
            True,
            1,
            True,
            False,
            True,
            "UNKNOWN",
            [],
        ),
    ]
    return spark.createDataFrame(rows, schema)


def _row(summary, grant_id, **values):
    frame = summary.where(F.col("grant_id") == grant_id)
    for key, value in values.items():
        frame = frame.withColumn(key, F.lit(value).cast(frame.schema[key].dataType))
    return frame


def _with_id(frame, grant_id):
    return frame.withColumn("grant_id", F.lit(grant_id))


def test_pd001_terminal_rules_and_precedence(spark):
    summary = _summary(spark)
    anchor_revoke = _with_id(_row(summary, "A"), "anchor-revoke")
    expected_high = _with_id(
        _row(
            summary,
            "B",
            expected_access_status="EXPECTED",
            expectation_evidence_strength="HIGH",
            certification_decision=None,
            certification_date=None,
            certification_campaign_id=None,
        ),
        "expected-high",
    )
    confirmed = _with_id(
        _row(
            summary,
            "B",
            expected_access_status="UNEXPECTED",
            expectation_evidence_strength="LOW",
            approval_relevance="CONFIRMED",
            approval_linkage_quality="DIRECT",
            approval_effective_at=date(2024, 5, 1),
            certification_decision=None,
            certification_date=None,
            certification_campaign_id=None,
        ),
        "confirmed",
    )
    blocking = _with_id(_row(summary, "C", data_quality_blocking=True), "blocking")
    outputs = build_policy_decisions(
        anchor_revoke.unionByName(expected_high)
        .unionByName(confirmed)
        .unionByName(blocking),
        load_policy_config(Path("configs/policy_decision.yml")),
        decided_at=EVALUATED,
    )
    rows = {row.grant_id: row for row in outputs.decisions.collect()}
    assert rows["anchor-revoke"].classification == "REVISAO"
    assert (
        rows["anchor-revoke"].winning_rule_id == "R015"
    )  # REVOKE wins over birthright
    assert rows["expected-high"].classification == "PADRAO"
    assert rows["expected-high"].winning_rule_id == "R030"
    assert rows["blocking"].classification == "REVISAO_DADOS"
    assert rows["blocking"].winning_rule_id == "R001"


def test_pd001_confirmed_direct_approval_and_conservative_fallback(spark):
    summary = _summary(spark)
    confirmed = _row(
        summary,
        "B",
        approval_relevance="CONFIRMED",
        approval_linkage_quality="DIRECT",
        approval_effective_at=date(2024, 5, 1),
        certification_decision=None,
        certification_date=None,
        certification_campaign_id=None,
    )
    inferred_public = _row(summary, "C")
    output = build_policy_decisions(
        confirmed.unionByName(inferred_public),
        load_policy_config(Path("configs/policy_decision.yml")),
        decided_at=EVALUATED,
    ).decisions
    rows = {row.grant_id: row for row in output.collect()}
    assert (rows["B"].classification, rows["B"].winning_rule_id) == ("LEGITIMO", "R040")
    assert (rows["C"].classification, rows["C"].winning_rule_id) == ("REVISAO", "R110")
    assert "INFERRED_APPROVAL_NOT_CONFIRMED" in rows["C"].supporting_reason_codes
    assert "PUBLIC_RELAXES_COMMUNITY_ONLY" in rows["C"].supporting_reason_codes


def test_pd001_rejects_future_evidence_and_preserves_grain(spark):
    summary = _summary(spark)
    duplicate = summary.unionByName(summary.where("grant_id = 'A'"))
    with pytest.raises(ValueError, match="grain"):
        build_policy_decisions(
            duplicate, load_policy_config(Path("configs/policy_decision.yml"))
        )
    future = summary.withColumn(
        "approval_effective_at",
        F.when(F.col("grant_id") == "B", F.lit(date(2025, 2, 2))).otherwise(
            F.col("approval_effective_at")
        ),
    )
    with pytest.raises(ValueError, match="Future"):
        build_policy_decisions(
            future, load_policy_config(Path("configs/policy_decision.yml"))
        )


def test_pd001_config_and_anti_leakage():
    config = load_policy_config(Path("configs/policy_decision.yml"))
    assert (config.policy_id, config.version) == ("PD001", "1.0.0")
    production = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in Path("src/sod_platform/access_intelligence/policy").glob("*.py")
    )
    assert "gabarito.csv" not in production
    assert "risk_score" not in production
    assert "machine_learning" not in production
