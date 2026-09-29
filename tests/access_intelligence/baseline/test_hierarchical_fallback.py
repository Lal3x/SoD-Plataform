from datetime import UTC, date, datetime
from pathlib import Path

from pyspark.sql import functions as F

from sod_platform.access_intelligence.baseline.fallback import (
    HierarchicalFallbackConfig,
    load_hierarchical_fallback_config,
    select_hierarchical_fallback,
)

BASELINE_SCHEMA = """
assessment_date date, baseline_level string, comunidade string, squad string,
cargo string, tipo_identidade string, entitlement_id string, population_size long,
support_count long, prevalence double, baseline_version string,
source_snapshot_id string, baseline_timestamp timestamp
"""
CONTEXT_SCHEMA = """
grant_id string, assessment_date date, entitlement_id string, comunidade string,
squad string, cargo string, tipo_identidade string
"""


def _baseline(spark):
    assessed = date(2025, 2, 1)
    timestamp = datetime(2025, 2, 1, tzinfo=UTC)
    return spark.createDataFrame(
        [
            (assessed, "SQUAD_CARGO_TIPO_IDENTIDADE", "Nova", "S1", "Analista", "employee", "E1", 1, 1, 1.0, "2.0.0", "specific", timestamp),
            (assessed, "COMUNIDADE_CARGO", "Nova", None, "Analista", None, "E1", 3, 2, 2 / 3, "2.0.0", "community-cargo", timestamp),
            (assessed, "COMUNIDADE", "Nova", None, None, None, "E1", 4, 2, 0.5, "2.0.0", "community", timestamp),
            (assessed, "POPULACAO_COMPARAVEL", None, None, None, "employee", "E1", 8, 3, 3 / 8, "2.0.0", "comparable-employees", timestamp),
            # A future assessment must never join a grant assessed in February.
            (date(2025, 3, 1), "SQUAD_CARGO_TIPO_IDENTIDADE", "Nova", "S1", "Analista", "employee", "E1", 100, 100, 1.0, "2.0.0", "future", datetime(2025, 3, 1, tzinfo=UTC)),
        ],
        BASELINE_SCHEMA,
    )


def _config():
    return HierarchicalFallbackConfig(2, 2, "2.0.0", "2.0.0")


def test_hierarchical_fallback_uses_next_sufficient_level_without_small_community_signal(spark):
    context = spark.createDataFrame(
        [("G1", date(2025, 2, 1), "E1", "Nova", "S1", "Analista", "employee")],
        CONTEXT_SCHEMA,
    )

    row = select_hierarchical_fallback(context, _baseline(spark), _config()).first()

    assert row.selected_baseline_level == "COMUNIDADE_CARGO"
    assert (row.selected_population_size, row.selected_support_count) == (3, 2)
    assert row.selection_status == "BASELINE_SELECTED"
    assert row.fallback_applied is True
    assert row.fallback_depth == 1
    assert "SQUAD_CARGO_TIPO_IDENTIDADE:INSUFFICIENT_ANALYTICAL_SUPPORT" in row.fallback_reason
    assert "suspeit" not in row.fallback_reason.lower()


def test_hierarchical_fallback_skips_missing_dimensions_then_uses_community(spark):
    context = spark.createDataFrame(
        [("G2", date(2025, 2, 1), "E1", "Nova", None, "Analista", "employee")],
        CONTEXT_SCHEMA,
    )

    row = select_hierarchical_fallback(context, _baseline(spark), _config()).first()

    assert row.selected_baseline_level == "COMUNIDADE_CARGO"
    assert "SQUAD_CARGO_TIPO_IDENTIDADE:MISSING_REQUIRED_DIMENSIONS" in row.fallback_reason


def test_hierarchical_fallback_uses_comparable_population_after_intermediate_levels_fail(spark):
    baseline = _baseline(spark).where("baseline_level <> 'COMUNIDADE_CARGO' AND baseline_level <> 'COMUNIDADE'")
    context = spark.createDataFrame(
        [("G3", date(2025, 2, 1), "E1", "Nova", "S1", "Analista", "employee")],
        CONTEXT_SCHEMA,
    )

    row = select_hierarchical_fallback(context, baseline, _config()).first()

    assert row.selected_baseline_level == "POPULACAO_COMPARAVEL"
    assert row.fallback_depth == 3


def test_hierarchical_fallback_handles_empty_baseline_as_insufficient_evidence(spark):
    context = spark.createDataFrame(
        [("G4", date(2025, 2, 1), "E1", "Nova", "S1", "Analista", "employee")],
        CONTEXT_SCHEMA,
    )
    empty = spark.createDataFrame([], BASELINE_SCHEMA)

    row = select_hierarchical_fallback(context, empty, _config()).first()

    assert row.selection_status == "INSUFFICIENT_EVIDENCE"
    assert row.selected_baseline_level is None
    assert row.baseline_sufficient is False
    assert row.fallback_depth == 4


def test_hierarchical_fallback_does_not_use_semantically_incompatible_population(spark):
    context = spark.createDataFrame(
        [("G5", date(2025, 2, 1), "E1", "Nova", "S1", "Analista", "contractor")],
        CONTEXT_SCHEMA,
    )
    employees_only = _baseline(spark).where(
        "baseline_level = 'POPULACAO_COMPARAVEL' AND tipo_identidade = 'employee'"
    )

    row = select_hierarchical_fallback(context, employees_only, _config()).first()

    assert row.selection_status == "INSUFFICIENT_EVIDENCE"
    assert row.selected_baseline_level is None
    assert row.fallback_depth == 4
    assert "POPULACAO_COMPARAVEL:BASELINE_NOT_AVAILABLE" in row.fallback_reason


def test_hierarchical_fallback_configuration_is_explicit_and_versioned():
    config = load_hierarchical_fallback_config(
        Path("configs/access_intelligence.yml")
    )

    assert config == HierarchicalFallbackConfig(2, 2, "2.0.0", "2.0.0")


def test_low_prevalence_with_sufficient_support_does_not_trigger_fallback(spark):
    baseline = _baseline(spark).withColumn(
        "population_size",
        F.when(F.col("baseline_level") == "SQUAD_CARGO_TIPO_IDENTIDADE", 20).otherwise(F.col("population_size")),
    ).withColumn(
        "support_count",
        F.when(F.col("baseline_level") == "SQUAD_CARGO_TIPO_IDENTIDADE", 2).otherwise(F.col("support_count")),
    ).withColumn(
        "prevalence",
        F.when(F.col("baseline_level") == "SQUAD_CARGO_TIPO_IDENTIDADE", .1).otherwise(F.col("prevalence")),
    )
    context = spark.createDataFrame(
        [("G6", date(2025, 2, 1), "E1", "Nova", "S1", "Analista", "employee")],
        CONTEXT_SCHEMA,
    )
    row = select_hierarchical_fallback(context, baseline, _config()).first()
    assert row.selected_baseline_level == "SQUAD_CARGO_TIPO_IDENTIDADE"
    assert row.selected_prevalence == .1
    assert row.fallback_applied is False
