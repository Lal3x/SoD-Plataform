"""Contracts for deterministic Expected Access decisioning."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pyspark.sql import functions as F

from sod_platform.access_intelligence.expected_access.engine import (
    ExpectedAccessConfig,
    build_expected_access,
    load_expected_access_config,
)

ASSESSED = date(2025, 2, 1)
TIMESTAMP = datetime(2025, 2, 1, tzinfo=UTC)
HTS_SCHEMA = """
grant_id string, assessment_date date, hard_trusted_flag boolean,
hard_trusted_reason string, hard_trusted_rule_id string,
hard_trusted_rule_version string, data_quality_blocking boolean,
source_snapshot_id string
"""
FALLBACK_SCHEMA = """
grant_id string, assessment_date date, selection_status string,
selected_baseline_level string, selected_population_size long,
selected_support_count long, selected_prevalence double,
baseline_sufficient boolean, fallback_depth integer, fallback_reason string,
fallback_version string, baseline_version string,
baseline_source_snapshot_id string, baseline_timestamp timestamp
"""


def _config():
    return ExpectedAccessConfig("EA001", "1.0.0", 0.80, 0.20, "2.0.0", "2.0.0")


def _inputs(spark):
    hts = spark.createDataFrame(
        [
            (
                "anchor",
                ASSESSED,
                True,
                "TRUSTED_BIRTHRIGHT_ANCHOR",
                "HTS001",
                "2.0.0",
                False,
                "s1",
            ),
            (
                "blocked",
                ASSESSED,
                True,
                "TRUSTED_BIRTHRIGHT_ANCHOR",
                "HTS001",
                "2.0.0",
                True,
                "s2",
            ),
            (
                "high",
                ASSESSED,
                False,
                "EXCLUDED_NOT_EXPLICIT_ANCHOR",
                "HTS001",
                "2.0.0",
                False,
                "s3",
            ),
            (
                "low",
                ASSESSED,
                False,
                "EXCLUDED_NOT_EXPLICIT_ANCHOR",
                "HTS001",
                "2.0.0",
                False,
                "s4",
            ),
            (
                "gray",
                ASSESSED,
                False,
                "EXCLUDED_NOT_EXPLICIT_ANCHOR",
                "HTS001",
                "2.0.0",
                False,
                "s5",
            ),
            (
                "high-boundary",
                ASSESSED,
                False,
                "EXCLUDED_NOT_EXPLICIT_ANCHOR",
                "HTS001",
                "2.0.0",
                False,
                "s6",
            ),
            (
                "low-boundary",
                ASSESSED,
                False,
                "EXCLUDED_NOT_EXPLICIT_ANCHOR",
                "HTS001",
                "2.0.0",
                False,
                "s7",
            ),
            (
                "no-baseline",
                ASSESSED,
                False,
                "EXCLUDED_NOT_EXPLICIT_ANCHOR",
                "HTS001",
                "2.0.0",
                False,
                "s8",
            ),
            (
                "broad",
                ASSESSED,
                False,
                "EXCLUDED_NOT_EXPLICIT_ANCHOR",
                "HTS001",
                "2.0.0",
                False,
                "s9",
            ),
            (
                "invalid",
                ASSESSED,
                False,
                "EXCLUDED_NOT_EXPLICIT_ANCHOR",
                "HTS001",
                "2.0.0",
                False,
                "s10",
            ),
            (
                "nulls",
                ASSESSED,
                False,
                "EXCLUDED_NOT_EXPLICIT_ANCHOR",
                "HTS001",
                "2.0.0",
                False,
                "s11",
            ),
        ],
        HTS_SCHEMA,
    )
    fallback = spark.createDataFrame(
        [
            (
                "anchor",
                ASSESSED,
                "BASELINE_SELECTED",
                "SQUAD_CARGO_TIPO_IDENTIDADE",
                100,
                10,
                0.10,
                True,
                0,
                "ok",
                "2.0.0",
                "2.0.0",
                "b1",
                TIMESTAMP,
            ),
            (
                "blocked",
                ASSESSED,
                "BASELINE_SELECTED",
                "SQUAD_CARGO_TIPO_IDENTIDADE",
                100,
                100,
                1.0,
                True,
                0,
                "ok",
                "2.0.0",
                "2.0.0",
                "b2",
                TIMESTAMP,
            ),
            (
                "high",
                ASSESSED,
                "BASELINE_SELECTED",
                "SQUAD_CARGO_TIPO_IDENTIDADE",
                100,
                81,
                0.81,
                True,
                0,
                "ok",
                "2.0.0",
                "2.0.0",
                "b3",
                TIMESTAMP,
            ),
            (
                "low",
                ASSESSED,
                "BASELINE_SELECTED",
                "SQUAD_CARGO_TIPO_IDENTIDADE",
                100,
                19,
                0.19,
                True,
                0,
                "ok",
                "2.0.0",
                "2.0.0",
                "b4",
                TIMESTAMP,
            ),
            (
                "gray",
                ASSESSED,
                "BASELINE_SELECTED",
                "SQUAD_CARGO_TIPO_IDENTIDADE",
                100,
                50,
                0.50,
                True,
                0,
                "ok",
                "2.0.0",
                "2.0.0",
                "b5",
                TIMESTAMP,
            ),
            (
                "high-boundary",
                ASSESSED,
                "BASELINE_SELECTED",
                "SQUAD_CARGO_TIPO_IDENTIDADE",
                100,
                80,
                0.80,
                True,
                0,
                "ok",
                "2.0.0",
                "2.0.0",
                "b6",
                TIMESTAMP,
            ),
            (
                "low-boundary",
                ASSESSED,
                "BASELINE_SELECTED",
                "SQUAD_CARGO_TIPO_IDENTIDADE",
                100,
                20,
                0.20,
                True,
                0,
                "ok",
                "2.0.0",
                "2.0.0",
                "b7",
                TIMESTAMP,
            ),
            (
                "no-baseline",
                ASSESSED,
                "INSUFFICIENT_EVIDENCE",
                None,
                None,
                None,
                None,
                False,
                4,
                "none",
                "2.0.0",
                "2.0.0",
                None,
                None,
            ),
            (
                "broad",
                ASSESSED,
                "BASELINE_SELECTED",
                "POPULACAO_COMPARAVEL",
                100,
                81,
                0.81,
                True,
                3,
                "ok",
                "2.0.0",
                "2.0.0",
                "b9",
                TIMESTAMP,
            ),
            (
                "invalid",
                ASSESSED,
                "BASELINE_SELECTED",
                "SQUAD_CARGO_TIPO_IDENTIDADE",
                10,
                11,
                1.10,
                True,
                0,
                "bad",
                "2.0.0",
                "2.0.0",
                "b10",
                TIMESTAMP,
            ),
            (
                "nulls",
                ASSESSED,
                "BASELINE_SELECTED",
                "SQUAD_CARGO_TIPO_IDENTIDADE",
                None,
                None,
                None,
                True,
                0,
                "bad",
                "2.0.0",
                "2.0.0",
                "b11",
                TIMESTAMP,
            ),
        ],
        FALLBACK_SCHEMA,
    )
    return hts, fallback


def test_expected_access_precedence_bands_strength_and_schema(spark):
    hts, fallback = _inputs(spark)
    output = build_expected_access(hts, fallback, _config())
    rows = {row.grant_id: row for row in output.collect()}

    assert (
        rows["anchor"].expected_access_status,
        rows["anchor"].expected_access_reason,
        rows["anchor"].expectation_evidence_strength,
    ) == ("EXPECTED", "EXPECTED_EXPLICIT_BIRTHRIGHT", "HIGH")
    assert (
        rows["blocked"].expected_access_reason == "INSUFFICIENT_ANALYTICAL_DATA_BLOCKED"
    )
    assert rows["high"].expected_access_status == "EXPECTED"
    assert rows["low"].expected_access_status == "UNEXPECTED"
    assert rows["gray"].expected_access_reason == "INSUFFICIENT_AMBIGUOUS_PREVALENCE"
    assert rows["high-boundary"].expected_access_status == "EXPECTED"
    assert rows["low-boundary"].expected_access_status == "UNEXPECTED"
    assert rows["no-baseline"].expected_access_reason == "INSUFFICIENT_NO_BASELINE"
    assert rows["high"].expectation_evidence_strength == "HIGH"
    assert rows["broad"].expected_access_status == rows["high"].expected_access_status
    assert rows["broad"].expectation_evidence_strength == "LOW"
    assert rows["invalid"].expected_access_reason == "INSUFFICIENT_ANALYTICAL_DATA"
    assert rows["nulls"].expected_access_reason == "INSUFFICIENT_ANALYTICAL_DATA"
    assert "machine_assessment" not in output.columns
    assert "legitimate" not in output.columns
    assert "inappropriate" not in output.columns


def test_expected_access_statuses_are_not_policy_outcomes(spark):
    hts, fallback = _inputs(spark)
    output = build_expected_access(hts, fallback, _config())
    statuses = {row.grant_id: row.expected_access_status for row in output.collect()}

    assert statuses["high"] == "EXPECTED"
    assert statuses["low"] == "UNEXPECTED"
    assert statuses["no-baseline"] == "INSUFFICIENT_EVIDENCE"
    assert set(statuses.values()) <= {
        "EXPECTED",
        "UNEXPECTED",
        "INSUFFICIENT_EVIDENCE",
    }
    assert (
        output.count()
        == output.select("grant_id", "assessment_date").distinct().count()
        == 11
    )
    assert output.columns == [
        "grant_id",
        "assessment_date",
        "expected_access_status",
        "expected_access_reason",
        "explicit_anchor_flag",
        "explicit_anchor_reason",
        "selected_baseline_level",
        "fallback_depth",
        "population_size",
        "support_count",
        "prevalence",
        "expectation_evidence_strength",
        "expected_access_method_id",
        "expected_access_method_version",
        "hard_trusted_rule_version",
        "baseline_version",
        "fallback_version",
        "source_snapshot_id",
        "baseline_source_snapshot_id",
        "baseline_timestamp",
        "evaluated_at",
    ]


def test_public_and_approval_fields_do_not_change_expected_access(spark):
    hts, fallback = _inputs(spark)
    enriched = hts.withColumn("sigla_publica", F.lit(True)).withColumn(
        "approval_relevance", F.lit("CONFIRMED")
    )
    original = build_expected_access(hts, fallback, _config()).select(
        "grant_id", "expected_access_status", "expected_access_reason"
    )
    repeated = build_expected_access(enriched, fallback, _config()).select(
        "grant_id", "expected_access_status", "expected_access_reason"
    )
    assert original.exceptAll(repeated).count() == 0
    assert repeated.exceptAll(original).count() == 0


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("baseline_version", "9.0.0", "baseline_version"),
        ("fallback_version", "9.0.0", "fallback_version"),
    ],
)
def test_incompatible_versions_are_rejected(spark, column, value, message):
    hts, fallback = _inputs(spark)
    with pytest.raises(ValueError, match=message):
        build_expected_access(hts, fallback.withColumn(column, F.lit(value)), _config())


def test_future_baseline_is_rejected(spark):
    hts, fallback = _inputs(spark)
    future = fallback.withColumn(
        "baseline_timestamp",
        F.when(
            F.col("grant_id") == "high", F.to_timestamp(F.lit("2025-02-02"))
        ).otherwise(F.col("baseline_timestamp")),
    )
    with pytest.raises(ValueError, match="Future baseline"):
        build_expected_access(hts, future, _config())


def test_grain_or_assessment_key_mismatch_is_rejected(spark):
    hts, fallback = _inputs(spark)
    duplicate = hts.unionByName(hts.where("grant_id = 'high'"))
    with pytest.raises(ValueError, match="grain"):
        build_expected_access(duplicate, fallback, _config())
    mismatch = fallback.withColumn(
        "assessment_date",
        F.when(F.col("grant_id") == "high", F.lit(date(2025, 2, 2))).otherwise(
            F.col("assessment_date")
        ),
    )
    with pytest.raises(ValueError, match="one-to-one match"):
        build_expected_access(hts, mismatch, _config())


def test_configuration_is_explicit_and_versioned():
    assert (
        load_expected_access_config(Path("configs/access_intelligence.yml"))
        == _config()
    )


def test_production_expected_access_has_no_validation_label_dependency():
    source = (
        Path("src/sod_platform/access_intelligence/expected_access/engine.py")
        .read_text(encoding="utf-8")
        .lower()
    )
    assert "gabarito.csv" not in source
    assert "cenario" not in source
    assert "expected label" not in source


def test_anchor_trust_and_unrelated_context_are_separate_from_expectedness(spark):
    hts, fallback = _inputs(spark)
    # The physical birthright flag, PUBLIC, approval, certification, usage,
    # contractor type and community relation are deliberately not EA inputs.
    enriched = (
        hts.withColumn("birthright", F.lit(True))
        .withColumn("sigla_publica", F.lit(True))
        .withColumn("approval_relevance", F.lit("CONFIRMED"))
        .withColumn("certification_decisao", F.lit("MAINTAIN"))
        .withColumn("tipo_atribuicao", F.lit("atribuido"))
        .withColumn("no_usage_recorded", F.lit(True))
        .withColumn("tipo_identidade", F.lit("contractor"))
        .withColumn("cross_community", F.lit(False))
    )
    enriched = enriched.withColumn(
        "hard_trusted_reason",
        F.when(F.col("grant_id") == "low", F.lit("EXCLUDED_EXPLICIT_CONTRADICTION"))
        .otherwise(F.col("hard_trusted_reason")),
    )
    rows = {r.grant_id: r for r in build_expected_access(enriched, fallback, _config()).collect()}
    assert rows["anchor"].expected_access_status == "EXPECTED"
    assert rows["anchor"].expectation_evidence_strength == "HIGH"
    assert rows["low"].expected_access_status == "UNEXPECTED"
    assert rows["low"].expected_access_reason == "UNEXPECTED_LOW_CONTEXT_PREVALENCE"
    assert rows["gray"].expected_access_status == "INSUFFICIENT_EVIDENCE"
    assert rows["no-baseline"].expected_access_status == "INSUFFICIENT_EVIDENCE"


def test_expected_access_is_deterministic_across_repartitioning(spark):
    hts, fallback = _inputs(spark)
    columns = [
        "grant_id", "assessment_date", "expected_access_status", "expected_access_reason",
        "expectation_evidence_strength", "selected_baseline_level", "population_size",
        "support_count", "prevalence", "expected_access_method_version",
    ]
    first = build_expected_access(hts, fallback, _config()).select(*columns)
    second = build_expected_access(hts.repartition(3), fallback.repartition(2), _config()).select(*columns)
    assert first.exceptAll(second).count() == 0
    assert second.exceptAll(first).count() == 0
