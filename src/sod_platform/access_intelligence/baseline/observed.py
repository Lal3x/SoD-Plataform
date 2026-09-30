"""Versioned observed prevalence from the valid observable population.

This module measures behaviour only.  Its output is deliberately not an
expected-access or legitimacy decision.
"""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

BASELINE_VERSION = "2.0.0"
REQUIRED_COLUMNS = {
    "assessment_date",
    "data_concessao",
    "entitlement_id",
    "identidade_id",
    "comunidade",
    "squad",
    "cargo",
    "tipo_identidade",
    "status_identidade",
    "cross_community",
    "data_quality_blocking",
}

# These are independent materializations.  Selecting between them is the
# future fallback stage; this stage never chooses a level for a grant.
BASELINE_LEVELS = (
    (
        "SQUAD_CARGO_TIPO_IDENTIDADE",
        ("comunidade", "squad", "cargo", "tipo_identidade"),
    ),
    ("COMUNIDADE_CARGO", ("comunidade", "cargo")),
    ("COMUNIDADE", ("comunidade",)),
    # Phase 1's broadest defensible comparison retains identity type.  It is
    # deliberately not an unrestricted bank-wide/global population.
    ("POPULACAO_COMPARAVEL", ("tipo_identidade",)),
)


def build_observed_baseline(
    observed_access: DataFrame, baseline_version: str = BASELINE_VERSION
) -> DataFrame:
    """Build prevalence statistics from valid, temporally relevant grants.

    ``population_size`` is the number of distinct observable identities in a
    population, while ``support_count`` is the distinct holders of an
    entitlement in that same population. Both are calculated per
    ``assessment_date``; a grant conceded after that date is excluded as a
    defensive temporal guard.
    """
    missing = REQUIRED_COLUMNS - set(observed_access.columns)
    if missing:
        raise ValueError(f"Observed Access missing baseline fields: {sorted(missing)}")
    if not baseline_version:
        raise ValueError("baseline_version must be non-empty")

    observable = observed_access.where(
        (~F.col("data_quality_blocking"))
        & (F.lower(F.col("status_identidade")) == "active")
        & (~F.coalesce(F.col("cross_community"), F.lit(True)))
        & F.col("data_concessao").isNotNull()
        & (F.col("data_concessao") <= F.col("assessment_date"))
    )
    results = [
        _build_level(observable, level, dimensions, baseline_version)
        for level, dimensions in BASELINE_LEVELS
    ]
    baseline = results[0]
    for result in results[1:]:
        baseline = baseline.unionByName(result)
    return baseline


def _build_level(
    observable: DataFrame,
    level: str,
    dimensions: tuple[str, ...],
    baseline_version: str,
) -> DataFrame:
    # Null context does not become a fictitious group.  The broader levels can
    # still describe the same identity, preserving information for fallback.
    comparable = observable
    for dimension in dimensions:
        comparable = comparable.where(F.col(dimension).isNotNull())

    population_keys = ["assessment_date", *dimensions]
    populations = comparable.groupBy(*population_keys).agg(
        F.countDistinct("identidade_id").alias("population_size")
    )
    support_keys = [*population_keys, "entitlement_id"]
    supports = comparable.groupBy(*support_keys).agg(
        F.countDistinct("identidade_id").alias("support_count"),
        _source_snapshot_expression(comparable).alias("source_snapshot_id"),
    )
    result = supports.join(populations, population_keys, "inner")
    for dimension in ("comunidade", "squad", "cargo", "tipo_identidade"):
        if dimension not in dimensions:
            result = result.withColumn(dimension, F.lit(None).cast("string"))
    return result.select(
        "assessment_date",
        F.lit(level).alias("baseline_level"),
        "comunidade",
        "squad",
        "cargo",
        "tipo_identidade",
        "entitlement_id",
        "population_size",
        "support_count",
        (F.col("support_count") / F.col("population_size"))
        .cast("double")
        .alias("prevalence"),
        F.lit(baseline_version).alias("baseline_version"),
        "source_snapshot_id",
        F.to_timestamp("assessment_date").alias("baseline_timestamp"),
    )


def _source_snapshot_expression(frame: DataFrame):
    """Return deterministic lineage for the records that support a statistic."""
    if "source_snapshot_id" not in frame.columns:
        return F.lit(None).cast("string")
    return F.sha2(
        F.concat_ws("|", F.sort_array(F.collect_set("source_snapshot_id"))), 256
    )
