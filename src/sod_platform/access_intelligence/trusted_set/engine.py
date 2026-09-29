"""Deterministic, contamination-resistant seeds for a future observed baseline."""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

RULE_ID = "HTS001"
RULE_VERSION = "2.1.0"
REQUIRED_CONTEXT_COLUMNS = {
    "grant_id",
    "assessment_date",
    "birthright",
    "cross_community",
    "sigla_publica",
    "certification_decisao",
    "data_quality_blocking",
}


def build_hard_trusted_set(access_context: DataFrame) -> DataFrame:
    """Annotate every context grant with a seed inclusion/exclusion reason.

    Birthright is the case-provided explicit anchor.  Neither frequency,
    public-sigla status, nor approval evidence creates an anchor. Public status
    only removes a community mismatch as a contradiction for an already
    explicit birthright anchor.
    """
    missing = REQUIRED_CONTEXT_COLUMNS - set(access_context.columns)
    if missing:
        raise ValueError(f"Access Context missing Hard Trusted Set fields: {sorted(missing)}")

    reason = (
        F.when(F.col("data_quality_blocking"), "EXCLUDED_BLOCKING_DQ")
        .when(~F.coalesce(F.col("birthright"), F.lit(False)), "EXCLUDED_NOT_EXPLICIT_ANCHOR")
        .when(F.col("certification_decisao") == "REVOKE", "EXCLUDED_EXPLICIT_CONTRADICTION")
        .when(
            F.coalesce(F.col("cross_community"), F.lit(True))
            & (~F.coalesce(F.col("sigla_publica"), F.lit(False))),
            "EXCLUDED_CONTEXT_CONFLICT",
        )
        .otherwise("TRUSTED_BIRTHRIGHT_ANCHOR")
    )
    return (
        access_context.withColumn("hard_trusted_reason", reason)
        .withColumn(
            "hard_trusted_flag",
            F.col("hard_trusted_reason") == "TRUSTED_BIRTHRIGHT_ANCHOR",
        )
        .withColumn("hard_trusted_rule_id", F.lit(RULE_ID))
        .withColumn("hard_trusted_rule_version", F.lit(RULE_VERSION))
    )
