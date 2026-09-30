"""Small, isolated architectural contracts for the post-Silver access context."""

from datetime import date, timedelta

import pytest
from pyspark.sql import functions as F

from sod_platform.access_intelligence.context.engine import build_access_context
from sod_platform.silver.accesses import transform as transform_accesses


def _tables(spark):
    identities = spark.createDataFrame(
        [("I1", "Credito", "S", "analista", "employee", "G", None, "active", None)],
        "identidade_id string, comunidade string, squad string, cargo string, tipo_identidade string, gestor string, data_entrada_comunidade_atual date, status_identidade string, data_desligamento date",
    )
    entitlements = spark.createDataFrame(
        [
            (
                "E1",
                "APP",
                "Credito",
                True,
                False,
                "OWNER",
                "HIGH",
                "INTERNAL",
                False,
                "NONE",
            )
        ],
        "entitlement_id string, sigla_id string, comunidade_dona_sigla string, birthright boolean, sigla_publica boolean, application_owner string, criticidade string, classificacao_dado string, privileged boolean, regulatory_scope string",
    )
    assignments = spark.createDataFrame(
        [
            ("G1", "I1", "E1", date(2024, 1, 1), "direct", None),
            ("G3", "I1", "E1", date(2026, 1, 1), "direct", None),
            ("G4", "I1", "E1", date(2024, 1, 1), "direct", None),
        ],
        "grant_id string, identidade_id string, entitlement_id string, data_concessao date, tipo_atribuicao string, ultimo_uso date",
    )
    approvals = spark.createDataFrame(
        [
            (
                "R1",
                "I1",
                "E1",
                "I1",
                date(2023, 12, 1),
                "APPROVED",
                "A",
                date(2024, 1, 2),
                "ok",
            ),
            (
                "R2",
                "I1",
                "E1",
                "I1",
                date(2023, 12, 1),
                "APPROVED",
                "B",
                date(2024, 1, 1),
                "old",
            ),
            (
                "R3",
                "I1",
                "E1",
                "I1",
                date(2023, 12, 1),
                "APPROVED",
                "C",
                date(2024, 1, 3),
                "unlinked",
            ),
        ],
        "request_id string, identidade_id string, entitlement_id string, solicitante string, data_solicitacao date, status_solicitacao string, aprovador string, data_aprovacao date, motivo string",
    )
    certifications = spark.createDataFrame(
        [
            ("C1", "I1", "E1", date(2024, 1, 1), "R", "MAINTAIN", "old"),
            ("C2", "I1", "E1", date(2024, 2, 1), "R", "REVOKE", "latest"),
            ("C3", "I1", "E1", None, None, "PENDING", None),
        ],
        "campaign_id string, identidade_id string, entitlement_id string, data_revisao date, revisor string, decisao string, justificativa string",
    )
    return {
        "identity_master": identities,
        "iga_entitlements": entitlements,
        "iga_access_assignments": assignments,
        "iga_access_requests": approvals,
        "access_certifications": certifications,
    }


def test_minimal_spark_session(spark):
    assert spark.range(1).count() == 1


def test_access_context_grain_temporal_joins_and_unknowns(spark):
    tables = _tables(spark)
    rows = {
        r.grant_id: r for r in build_access_context(tables, date(2025, 2, 1)).collect()
    }

    assert set(rows) == {"G1", "G4"}
    assert len(rows) == 2
    assert rows["G1"].approval_relevance == "UNCERTAIN"
    assert rows["G1"].approval_linkage_quality == "STRONG_INFERRED"
    assert rows["G1"].aprovador == "B"
    assert rows["G4"].approval_relevance == "UNCERTAIN"
    assert rows["G1"].certification_decisao == "REVOKE"
    assert rows["G1"].certification_pending_count == 1
    assert rows["G1"].usage_coverage == "UNKNOWN"
    assert rows["G1"].birthright is True
    assert rows["G1"].sigla_publica is False
    assert rows["G1"].cross_community is False
    assert rows["G1"].criticidade == "HIGH"
    assert rows["G1"].privileged is False
    assert rows["G1"].access_age_days == 397
    assert rows["G1"].no_usage_recorded is True
    assert rows["G1"].identity_history_complete is False
    assert rows["G1"].inherited_access_candidate is None
    assert not {
        "cenario",
        "classificacao_esperada",
        "expected_class",
        "ground_truth",
    }.intersection(rows["G1"].asDict())
    without_approvals = {
        name: frame for name, frame in tables.items() if name != "iga_access_requests"
    }
    assert (
        build_access_context(without_approvals, date(2025, 2, 1))
        .where("grant_id = 'G1'")
        .first()
        .approval_relevance
        == "NOT_FOUND"
    )


def test_technical_grant_key_is_deterministic_and_traceable(spark):
    raw = spark.createDataFrame(
        [("I1", "E1", "2024-01-01", "direct", None)],
        "identidade_id string, entitlement_id string, data_concessao string, tipo_atribuicao string, ultimo_uso string",
    ).withColumn("_source_file", F.lit("legacy.csv"))
    first = transform_accesses(raw, ["yyyy-MM-dd"]).first()
    second = transform_accesses(raw, ["yyyy-MM-dd"]).first()

    assert first.grant_id == second.grant_id
    assert first.grant_id.startswith("technical-")
    assert first.grant_id_generated is True
    assert first.grant_id_generation_method == "SHA256_IDENTITY_ENTITLEMENT_V2"


def test_access_context_does_not_require_native_request_to_grant_link(spark):
    tables = _tables(spark)

    row = (
        build_access_context(tables, date(2025, 2, 1)).where("grant_id = 'G1'").first()
    )

    assert row.approval_relevance == "UNCERTAIN"


@pytest.mark.parametrize("delta_days", [0, 1, 2, 7, 30])
def test_access_context_marks_unique_temporally_coherent_approval_as_strong_inferred(
    spark, delta_days
):
    tables = _tables(spark)
    approval_date = date(2024, 1, 1) - timedelta(days=delta_days)
    tables["iga_access_requests"] = spark.createDataFrame(
        [
            (
                "R-UNIQUE",
                "I1",
                "E1",
                "I1",
                date(2023, 12, 1),
                "APPROVED",
                "A",
                approval_date,
                "unique temporally coherent inferred match",
            )
        ],
        "request_id string, identidade_id string, entitlement_id string, solicitante string, data_solicitacao date, status_solicitacao string, aprovador string, data_aprovacao date, motivo string",
    )

    row = (
        build_access_context(tables, date(2025, 2, 1)).where("grant_id = 'G1'").first()
    )

    assert row.approval_relevance == "UNCERTAIN"
    assert row.approval_linkage_quality == "STRONG_INFERRED"
    assert row.request_id == "R-UNIQUE"
    assert row.approval_to_grant_delta_days == delta_days


def test_access_context_does_not_overfit_strong_inference_to_one_day_delta(spark):
    tables = _tables(spark)
    tables["iga_access_requests"] = spark.createDataFrame(
        [
            (
                "R-SEVEN-DAYS",
                "I1",
                "E1",
                "I1",
                date(2023, 12, 1),
                "APPROVED",
                "A",
                date(2023, 12, 25),
                "must remain strong inferred",
            )
        ],
        "request_id string, identidade_id string, entitlement_id string, solicitante string, data_solicitacao date, status_solicitacao string, aprovador string, data_aprovacao date, motivo string",
    )

    row = (
        build_access_context(tables, date(2025, 2, 1)).where("grant_id = 'G1'").first()
    )

    assert row.approval_relevance == "UNCERTAIN"
    assert row.approval_linkage_quality == "STRONG_INFERRED"
    assert row.approval_to_grant_delta_days == 7


def test_access_context_marks_multiple_temporal_candidates_as_ambiguous(spark):
    tables = _tables(spark)
    tables["iga_access_requests"] = spark.createDataFrame(
        [
            (
                "R-ONE",
                "I1",
                "E1",
                "I1",
                date(2023, 12, 1),
                "APPROVED",
                "A",
                date(2023, 12, 31),
                "one",
            ),
            (
                "R-FIVE",
                "I1",
                "E1",
                "I1",
                date(2023, 12, 1),
                "APPROVED",
                "B",
                date(2023, 12, 27),
                "five",
            ),
        ],
        "request_id string, identidade_id string, entitlement_id string, solicitante string, data_solicitacao date, status_solicitacao string, aprovador string, data_aprovacao date, motivo string",
    )

    row = (
        build_access_context(tables, date(2025, 2, 1)).where("grant_id = 'G1'").first()
    )

    assert row.approval_relevance == "UNCERTAIN"
    assert row.approval_linkage_quality == "AMBIGUOUS"


def test_access_context_excludes_missing_approver_from_strong_inference(spark):
    tables = _tables(spark)
    tables["iga_access_requests"] = spark.createDataFrame(
        [
            (
                "R-NO-APPROVER",
                "I1",
                "E1",
                "I1",
                date(2023, 12, 1),
                "APPROVED",
                None,
                date(2023, 12, 31),
                "missing approver",
            ),
        ],
        "request_id string, identidade_id string, entitlement_id string, solicitante string, data_solicitacao date, status_solicitacao string, aprovador string, data_aprovacao date, motivo string",
    )

    row = (
        build_access_context(tables, date(2025, 2, 1)).where("grant_id = 'G1'").first()
    )

    assert row.approval_relevance == "NOT_FOUND"
    assert row.approval_linkage_quality == "UNKNOWN"


def test_access_context_excludes_approval_after_grant_from_strong_inference(spark):
    tables = _tables(spark)
    tables["iga_access_requests"] = spark.createDataFrame(
        [
            (
                "R-AFTER",
                "I1",
                "E1",
                "I1",
                date(2023, 12, 1),
                "APPROVED",
                "A",
                date(2024, 1, 2),
                "after grant",
            ),
        ],
        "request_id string, identidade_id string, entitlement_id string, solicitante string, data_solicitacao date, status_solicitacao string, aprovador string, data_aprovacao date, motivo string",
    )

    row = (
        build_access_context(tables, date(2025, 2, 1)).where("grant_id = 'G1'").first()
    )

    assert row.approval_relevance == "NOT_FOUND"
    assert row.approval_linkage_quality == "UNKNOWN"
