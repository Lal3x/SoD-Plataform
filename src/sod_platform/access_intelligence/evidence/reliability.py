"""Transparent, deterministic reliability mappings for individual facts."""

from pyspark.sql import Column
from pyspark.sql import functions as F


def direct_reliability(value: Column) -> Column:
    return F.when(value.isNotNull(), F.lit("HIGH")).otherwise(F.lit("UNKNOWN"))


def approval_reliability(value: Column, linkage_quality: Column) -> Column:
    """Rate approval evidence without promoting inferred linkage to direct."""
    return (
        F.when(value == "CONFIRMED", "HIGH")
        .when(
            (value == "UNCERTAIN") & (linkage_quality == "STRONG_INFERRED"),
            "MEDIUM",
        )
        .when(value == "UNCERTAIN", "LOW")
        .otherwise("UNKNOWN")
    )


def certification_reliability(decision: Column, reviewed_at: Column, record_id: Column) -> Column:
    return F.when(
        decision.isNotNull() & reviewed_at.isNotNull() & record_id.isNotNull(),
        "HIGH",
    ).otherwise("UNKNOWN")


def expected_access_reliability(status: Column, strength: Column) -> Column:
    return (
        F.when(status == "INSUFFICIENT_EVIDENCE", "UNKNOWN")
        .when(strength == "HIGH", "HIGH")
        .when(strength == "MEDIUM", "MEDIUM")
        .when(strength == "LOW", "LOW")
        .otherwise("UNKNOWN")
    )


def inherited_reliability(candidate: Column, history_complete: Column) -> Column:
    return (
        F.when(candidate.isNull(), "UNKNOWN")
        .when(candidate & (~F.coalesce(history_complete, F.lit(False))), "LOW")
        .otherwise("HIGH")
    )


def coverage_reliability(coverage: Column) -> Column:
    return (
        F.when(coverage == "COMPLETE", "HIGH")
        .when(coverage == "PARTIAL", "MEDIUM")
        .otherwise("UNKNOWN")
    )
