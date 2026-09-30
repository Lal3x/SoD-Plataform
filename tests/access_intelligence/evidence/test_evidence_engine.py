"""EV001 contracts: evidence is preserved without policy interpretation."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pyspark.sql import functions as F

from sod_platform.access_intelligence.evidence.contract import (
    EvidenceEngineConfig,
    load_evidence_engine_config,
)
from sod_platform.access_intelligence.evidence.engine import (
    _match_requests,
    build_evidence,
)

ASSESSED = date(2025, 2, 1)
EVALUATED = datetime(2025, 2, 1, 12, tzinfo=UTC)

CONTEXT_SCHEMA = """
grant_id string, assessment_date date, _silver_run_id string,
identidade_id string, entitlement_id string, sigla_id string,
birthright boolean, sigla_publica boolean, cross_community boolean,
approval_relevance string, approval_linkage_quality string, request_id string,
data_aprovacao date, certification_decisao string,
certification_data_revisao date, certification_campaign_id string,
certification_pending_count long, data_concessao date, ultimo_uso date,
inherited_access_candidate boolean, identity_history_complete boolean,
no_usage_recorded boolean, usage_coverage string, access_age_days integer,
days_since_last_use integer, entitlement_privileged boolean,
application_criticality string, classificacao_dado string,
regulatory_scope string, data_quality_blocking boolean, source_snapshot_id string
"""

EXPECTED_SCHEMA = """
grant_id string, assessment_date date, expected_access_status string,
expected_access_reason string, explicit_anchor_flag boolean,
explicit_anchor_reason string, selected_baseline_level string,
fallback_depth integer, population_size long, support_count long,
prevalence double, expectation_evidence_strength string,
expected_access_method_id string, expected_access_method_version string,
hard_trusted_rule_version string, baseline_version string,
fallback_version string, source_snapshot_id string,
baseline_source_snapshot_id string, baseline_timestamp timestamp,
evaluated_at timestamp
"""


def _config():
    return EvidenceEngineConfig(
        "EV001", "1.3.1", "EA001", "1.0.0", "2.1.0", "2.0.0", "2.0.0"
    )


def _inputs(spark):
    context = spark.createDataFrame(
        [
            (
                "A",
                ASSESSED,
                "run-1",
                "I1",
                "E1",
                "S1",
                True,
                False,
                False,
                "NOT_FOUND",
                None,
                None,
                None,
                "REVOKE",
                date(2025, 1, 10),
                "C1",
                0,
                date(2024, 1, 1),
                None,
                False,
                False,
                True,
                "UNKNOWN",
                397,
                None,
                False,
                "LOW",
                "INTERNAL",
                "NONE",
                False,
                "snapshot-a",
            ),
            (
                "B",
                ASSESSED,
                "run-1",
                "I2",
                "E2",
                "S2",
                False,
                False,
                True,
                "CONFIRMED",
                "DIRECT_FUTURE_COMPATIBLE",
                "R2",
                date(2024, 5, 1),
                "MAINTAIN",
                date(2025, 1, 12),
                "C2",
                0,
                date(2024, 6, 1),
                date(2025, 1, 1),
                False,
                False,
                False,
                "COMPLETE",
                245,
                31,
                True,
                "CRITICAL",
                "RESTRICTED",
                "BACEN",
                False,
                "snapshot-b",
            ),
            (
                "C",
                ASSESSED,
                "run-1",
                "I3",
                "E3",
                "S3",
                False,
                True,
                None,
                "UNCERTAIN",
                "STRONG_INFERRED",
                "R3",
                date(2024, 7, 1),
                None,
                None,
                None,
                1,
                date(2024, 8, 1),
                None,
                True,
                False,
                True,
                "UNKNOWN",
                184,
                None,
                None,
                None,
                None,
                None,
                False,
                "snapshot-c",
            ),
        ],
        CONTEXT_SCHEMA,
    ).withColumns(
        {
            "tipo_identidade": F.when(F.col("grant_id") == "C", "contractor").otherwise(
                "employee"
            ),
            "comunidade": F.when(F.col("grant_id") == "C", "Tecnologia").otherwise(
                "Credito"
            ),
            "squad": F.concat(F.lit("Squad-"), F.col("grant_id")),
            "cargo": F.when(F.col("grant_id") == "C", "Engineer").otherwise("Analyst"),
            "comunidade_dona_sigla": F.when(
                F.col("grant_id") == "C", "Negocios"
            ).otherwise("Credito"),
        }
    )
    expected = spark.createDataFrame(
        [
            (
                "A",
                ASSESSED,
                "EXPECTED",
                "EXPECTED_EXPLICIT_BIRTHRIGHT",
                True,
                "TRUSTED_BIRTHRIGHT_ANCHOR",
                "SQUAD_CARGO_TIPO_IDENTIDADE",
                0,
                10,
                10,
                1.0,
                "HIGH",
                "EA001",
                "1.0.0",
                "2.1.0",
                "2.0.0",
                "2.0.0",
                "snapshot-a",
                "baseline-a",
                EVALUATED,
                EVALUATED,
            ),
            (
                "B",
                ASSESSED,
                "UNEXPECTED",
                "UNEXPECTED_LOW_CONTEXT_PREVALENCE",
                False,
                "EXCLUDED_NOT_EXPLICIT_ANCHOR",
                "POPULACAO_COMPARAVEL",
                3,
                100,
                10,
                0.1,
                "LOW",
                "EA001",
                "1.0.0",
                "2.1.0",
                "2.0.0",
                "2.0.0",
                "snapshot-b",
                "baseline-b",
                EVALUATED,
                EVALUATED,
            ),
            (
                "C",
                ASSESSED,
                "INSUFFICIENT_EVIDENCE",
                "INSUFFICIENT_NO_BASELINE",
                False,
                "EXCLUDED_NOT_EXPLICIT_ANCHOR",
                None,
                4,
                None,
                None,
                None,
                None,
                "EA001",
                "1.0.0",
                "2.1.0",
                "2.0.0",
                "2.0.0",
                "snapshot-c",
                None,
                EVALUATED,
                EVALUATED,
            ),
        ],
        EXPECTED_SCHEMA,
    )
    return context, expected


def test_v2_request_matching_distinguishes_observable_states(spark):
    context = spark.createDataFrame(
        [
            ("unique", ASSESSED, "I1", "E1", date(2025, 1, 20), "NOT_FOUND", "UNKNOWN"),
            (
                "multiple",
                ASSESSED,
                "I2",
                "E2",
                date(2025, 1, 20),
                "NOT_FOUND",
                "UNKNOWN",
            ),
            (
                "conflict",
                ASSESSED,
                "I3",
                "E3",
                date(2025, 1, 20),
                "NOT_FOUND",
                "UNKNOWN",
            ),
            ("absent", ASSESSED, "I4", "E4", date(2025, 1, 20), "NOT_FOUND", "UNKNOWN"),
        ],
        "grant_id string, assessment_date date, identidade_id string, entitlement_id string, data_concessao date, approval_relevance string, approval_linkage_quality string",
    )
    requests = spark.createDataFrame(
        [
            ("R1", "I1", "E1", "APPROVED", date(2025, 1, 1), date(2025, 1, 2), "A"),
            ("R2", "I2", "E2", "APPROVED", date(2025, 1, 1), date(2025, 1, 2), "A"),
            ("R3", "I2", "E2", "APPROVED", date(2025, 1, 3), date(2025, 1, 4), "B"),
            ("R4", "I3", "E3", "APPROVED", date(2025, 1, 21), date(2025, 1, 22), "A"),
        ],
        "request_id string, identidade_id string, entitlement_id string, status_solicitacao string, data_solicitacao date, data_aprovacao date, aprovador string",
    )
    rows = {row.grant_id: row for row in _match_requests(context, requests).collect()}
    assert len(rows) == 4
    assert rows["unique"].approval_evidence_status == "UNIQUE_MATCH"
    assert rows["unique"].approval_linkage_quality == "STRONG_INFERRED"
    assert rows["multiple"].approval_evidence_status == "MULTIPLE_CANDIDATES"
    assert rows["conflict"].approval_evidence_status == "TEMPORAL_CONFLICT"
    assert rows["absent"].approval_evidence_status == "NOT_FOUND"
    assert all(row.approval_linkage_quality != "DIRECT" for row in rows.values())
    assert all(row.approval_evidence_status != "UNAUTHORIZED" for row in rows.values())
    repartitioned = {
        row.grant_id: row
        for row in _match_requests(
            context.repartition(3), requests.repartition(2)
        ).collect()
    }
    assert {
        key: (row.approval_evidence_status, row.approval_candidate_count)
        for key, row in rows.items()
    } == {
        key: (row.approval_evidence_status, row.approval_candidate_count)
        for key, row in repartitioned.items()
    }


def test_ev001_preserves_grain_semantics_reliability_and_mixed_evidence(spark):
    context, expected = _inputs(spark)
    outputs = build_evidence(context, expected, _config(), evaluated_at=EVALUATED)
    rows = {row.grant_id: row for row in outputs.summary.collect()}

    assert len(rows) == 3
    assert outputs.summary.select("grant_id", "assessment_date").distinct().count() == 3
    assert rows["A"].expected_access_status == "EXPECTED"
    assert rows["A"].contradiction_codes == [
        "CX001_BIRTHRIGHT_ANCHOR_WITH_REVOKE_CERTIFICATION"
    ]
    assert rows["B"].expected_access_status == "UNEXPECTED"
    assert rows["B"].expectation_evidence_strength == "LOW"
    assert rows["B"].mixed_evidence_codes == [
        "MX001_UNEXPECTED_WITH_CONFIRMED_APPROVAL",
        "MX002_UNEXPECTED_WITH_MAINTAIN_CERTIFICATION",
    ]
    assert rows["B"].contradiction_codes == []
    assert rows["C"].community_relation == "UNKNOWN"
    assert rows["C"].identity_type == "contractor"
    assert rows["C"].identity_community == "Tecnologia"
    assert rows["C"].owner_community == "Negocios"
    assert rows["C"].squad == "Squad-C"
    assert rows["C"].cargo == "Engineer"
    assert rows["A"].certification_status == "REVOKE"
    assert rows["B"].certification_status == "MAINTAIN"
    assert rows["C"].certification_status == "PENDING"
    assert rows["C"].mixed_evidence_codes == [
        "MX003_PUBLIC_WITH_INSUFFICIENT_EXPECTATION",
        "MX004_INHERITED_CANDIDATE_WITH_INCOMPLETE_HISTORY",
    ]
    assert "machine_assessment" not in outputs.summary.columns
    assert "impact" not in outputs.summary.columns
    assert "priority" not in outputs.summary.columns
    assert "polarity" not in outputs.facts.columns
    assert outputs.facts.where("evidence_bundle_id is null").count() == 0

    facts = {(row.grant_id, row.evidence_type): row for row in outputs.facts.collect()}
    assert facts[("B", "APPROVAL_RELEVANCE")].evidence_value == "CONFIRMED"
    assert facts[("B", "APPROVAL_RELEVANCE")].evidence_reliability == "HIGH"
    assert facts[("C", "APPROVAL_RELEVANCE")].evidence_value == "UNCERTAIN"
    assert facts[("C", "APPROVAL_RELEVANCE")].evidence_reliability == "MEDIUM"
    assert (
        facts[("C", "APPROVAL_RELEVANCE")].reliability_reason_code
        == "STRONG_INFERRED_LINKAGE"
    )
    assert facts[("A", "APPROVAL_RELEVANCE")].evidence_reliability == "UNKNOWN"
    assert facts[("B", "EXPECTED_ACCESS")].evidence_reliability == "LOW"
    assert facts[("C", "EXPECTED_ACCESS")].evidence_reliability == "UNKNOWN"
    assert facts[("C", "USAGE_OBSERVATION")].evidence_value == "NO_USAGE_RECORDED"
    assert facts[("C", "USAGE_OBSERVATION")].evidence_reliability == "UNKNOWN"
    assert facts[("C", "INHERITED_ACCESS_CANDIDATE")].evidence_reliability == "LOW"
    assert facts[("C", "CERTIFICATION_PENDING")].evidence_reliability == "LOW"
    assert facts[("C", "IDENTITY_TYPE")].evidence_value == "contractor"
    assert facts[("C", "IDENTITY_COMMUNITY")].evidence_value == "Tecnologia"
    assert facts[("C", "ENTITLEMENT_OWNER_COMMUNITY")].evidence_value == "Negocios"
    assert facts[("C", "IDENTITY_SQUAD")].evidence_value == "Squad-C"
    assert facts[("C", "IDENTITY_ROLE")].evidence_value == "Engineer"


def test_ev001_emits_explicit_certification_not_found_exclusively(spark):
    context, expected = _inputs(spark)
    context = context.withColumn(
        "certification_pending_count",
        F.when(F.col("grant_id") == "C", F.lit(0)).otherwise(
            F.col("certification_pending_count")
        ),
    )
    outputs = build_evidence(context, expected, _config(), evaluated_at=EVALUATED)
    summary = {row.grant_id: row for row in outputs.summary.collect()}
    assert summary["C"].certification_status == "CERTIFICATION_NOT_FOUND"
    assert all(row.certification_status is not None for row in summary.values())
    states = outputs.facts.where(
        F.col("evidence_type").isin(
            "CERTIFICATION_DECISION", "CERTIFICATION_PENDING", "CERTIFICATION_NOT_FOUND"
        )
    )
    assert states.groupBy("grant_id").count().where("count > 1").count() == 0
    assert (
        states.where(
            (F.col("grant_id") == "C")
            & (F.col("evidence_type") == "CERTIFICATION_NOT_FOUND")
        ).count()
        == 1
    )


def test_ev001_is_deterministic_and_does_not_duplicate_evidence(spark):
    context, expected = _inputs(spark)
    first = build_evidence(context, expected, _config(), evaluated_at=EVALUATED)
    second = build_evidence(context, expected, _config(), evaluated_at=EVALUATED)

    comparable_first = first.facts.withColumn(
        "evidence_attributes", F.to_json("evidence_attributes")
    )
    comparable_second = second.facts.withColumn(
        "evidence_attributes", F.to_json("evidence_attributes")
    )
    assert comparable_first.exceptAll(comparable_second).count() == 0
    assert comparable_second.exceptAll(comparable_first).count() == 0
    assert first.summary.exceptAll(second.summary).count() == 0
    assert second.summary.exceptAll(first.summary).count() == 0
    assert first.facts.count() == first.facts.select("evidence_id").distinct().count()


def test_ev001_rejects_grain_key_version_and_future_evidence(spark):
    context, expected = _inputs(spark)
    duplicate = context.unionByName(context.where("grant_id = 'A'"))
    with pytest.raises(ValueError, match="grain"):
        build_evidence(duplicate, expected, _config())

    missing = expected.where("grant_id != 'A'")
    with pytest.raises(ValueError, match="one-to-one match"):
        build_evidence(context, missing, _config())

    incompatible = expected.withColumn("baseline_version", F.lit("9.0.0"))
    with pytest.raises(ValueError, match="baseline_version"):
        build_evidence(context, incompatible, _config())

    future = context.withColumn(
        "ultimo_uso",
        F.when(F.col("grant_id") == "A", F.lit(date(2025, 2, 2))).otherwise(
            F.col("ultimo_uso")
        ),
    )
    with pytest.raises(ValueError, match="Future"):
        build_evidence(future, expected, _config())


def test_ev001_configuration_and_anti_leakage():
    assert load_evidence_engine_config(Path("configs/evidence_engine.yml")) == _config()
    production = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in Path("src/sod_platform/access_intelligence/evidence").glob("*.py")
    )
    assert "gabarito.csv" not in production
    assert "cenario" not in production
    assert "risk_score" not in production
    assert "legitimacy_score" not in production
