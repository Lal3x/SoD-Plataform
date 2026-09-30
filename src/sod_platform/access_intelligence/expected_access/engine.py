"""Deterministic analytical expectation after hierarchical fallback.

Expected Access measures adherence to an observed comparable pattern. It does
not decide authorization, legitimacy, policy compliance, risk, or final SoD
classification.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

EXPECTED = "EXPECTED"
UNEXPECTED = "UNEXPECTED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

REQUIRED_HTS_COLUMNS = {
    "grant_id",
    "assessment_date",
    "hard_trusted_flag",
    "hard_trusted_reason",
    "hard_trusted_rule_id",
    "hard_trusted_rule_version",
    "data_quality_blocking",
    "source_snapshot_id",
}
REQUIRED_FALLBACK_COLUMNS = {
    "grant_id",
    "assessment_date",
    "selection_status",
    "selected_baseline_level",
    "selected_population_size",
    "selected_support_count",
    "selected_prevalence",
    "baseline_sufficient",
    "fallback_depth",
    "fallback_reason",
    "fallback_version",
    "baseline_version",
    "baseline_source_snapshot_id",
    "baseline_timestamp",
}
STRENGTH_BY_LEVEL = {
    "SQUAD_CARGO_TIPO_IDENTIDADE": "HIGH",
    "COMUNIDADE_CARGO": "MEDIUM",
    "COMUNIDADE": "MEDIUM",
    "POPULACAO_COMPARAVEL": "LOW",
}
NUMERIC_TOLERANCE = 1e-12


@dataclass(frozen=True)
class ExpectedAccessConfig:
    """Versioned POC parameters, independent from institutional policy."""

    method_id: str
    version: str
    expected_prevalence_threshold: float
    unexpected_prevalence_threshold: float
    supported_baseline_version: str
    supported_fallback_version: str

    def __post_init__(self) -> None:
        if not all(
            (
                self.method_id,
                self.version,
                self.supported_baseline_version,
                self.supported_fallback_version,
            )
        ):
            raise ValueError(
                "Expected Access identifiers and versions must be non-empty"
            )
        if not (
            0
            <= self.unexpected_prevalence_threshold
            < self.expected_prevalence_threshold
            <= 1
        ):
            raise ValueError(
                "Expected Access thresholds must satisfy 0 <= unexpected < expected <= 1"
            )


def load_expected_access_config(path: Path) -> ExpectedAccessConfig:
    """Load explicit, versioned Expected Access parameters."""
    try:
        values = yaml.safe_load(path.read_text(encoding="utf-8"))["expected_access"]
        return ExpectedAccessConfig(
            method_id=str(values["method_id"]),
            version=str(values["version"]),
            expected_prevalence_threshold=float(
                values["expected_prevalence_threshold"]
            ),
            unexpected_prevalence_threshold=float(
                values["unexpected_prevalence_threshold"]
            ),
            supported_baseline_version=str(values["supported_baseline_version"]),
            supported_fallback_version=str(values["supported_fallback_version"]),
        )
    except (KeyError, OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        raise ValueError(
            f"Invalid Expected Access configuration {path}: {exc}"
        ) from exc


def build_expected_access(
    hard_trusted_set: DataFrame,
    hierarchical_fallback: DataFrame,
    config: ExpectedAccessConfig,
) -> DataFrame:
    """Return one analytical expectation for every grant/date input key."""
    _require_columns(hard_trusted_set, REQUIRED_HTS_COLUMNS, "Hard Trusted Set")
    _require_columns(
        hierarchical_fallback, REQUIRED_FALLBACK_COLUMNS, "Hierarchical Fallback"
    )
    _validate_one_to_one_contract(hard_trusted_set, hierarchical_fallback)
    _validate_versions_and_time(hierarchical_fallback, config)

    hts = hard_trusted_set.select(*sorted(REQUIRED_HTS_COLUMNS)).alias("h")
    fallback = hierarchical_fallback.select(*sorted(REQUIRED_FALLBACK_COLUMNS)).alias(
        "f"
    )
    frame = hts.join(fallback, ["grant_id", "assessment_date"], "inner")

    baseline_available = (
        (F.col("selection_status") == "BASELINE_SELECTED")
        & F.col("baseline_sufficient")
        & F.col("selected_baseline_level").isNotNull()
    )
    expected_prevalence = F.col("selected_support_count") / F.col(
        "selected_population_size"
    )
    invalid_contract_data = (
        F.col("data_quality_blocking").isNull()
        | F.col("hard_trusted_flag").isNull()
        | (~F.col("selection_status").isin("BASELINE_SELECTED", INSUFFICIENT_EVIDENCE))
        | (
            (F.col("selection_status") == "BASELINE_SELECTED")
            & F.col("baseline_sufficient").isNull()
        )
    )
    invalid_baseline_data = baseline_available & (
        F.col("selected_population_size").isNull()
        | F.col("selected_support_count").isNull()
        | F.col("selected_prevalence").isNull()
        | F.col("baseline_timestamp").isNull()
        | (F.col("selected_population_size") <= 0)
        | (F.col("selected_support_count") < 0)
        | (F.col("selected_support_count") > F.col("selected_population_size"))
        | (F.col("selected_prevalence") < 0)
        | (F.col("selected_prevalence") > 1)
        | (
            F.abs(F.col("selected_prevalence") - expected_prevalence)
            > F.lit(NUMERIC_TOLERANCE)
        )
        | (~F.col("selected_baseline_level").isin(*STRENGTH_BY_LEVEL))
    )
    invalid_analytical_data = invalid_contract_data | invalid_baseline_data
    no_baseline = (
        (F.col("selection_status") == INSUFFICIENT_EVIDENCE)
        | (~F.coalesce(F.col("baseline_sufficient"), F.lit(False)))
        | F.col("selected_baseline_level").isNull()
    )
    status, reason = _decision_columns(
        config, invalid_analytical_data=invalid_analytical_data, no_baseline=no_baseline
    )
    strength = (
        F.when(F.col("data_quality_blocking"), F.lit(None).cast("string"))
        .when(invalid_analytical_data, F.lit(None).cast("string"))
        .when(F.col("hard_trusted_flag"), F.lit("HIGH"))
        .when(no_baseline, F.lit(None).cast("string"))
    )
    for level, value in STRENGTH_BY_LEVEL.items():
        strength = strength.when(F.col("selected_baseline_level") == level, value)
    strength = strength.otherwise(F.lit(None).cast("string"))

    return frame.select(
        "grant_id",
        "assessment_date",
        status.alias("expected_access_status"),
        reason.alias("expected_access_reason"),
        F.col("hard_trusted_flag").alias("explicit_anchor_flag"),
        F.col("hard_trusted_reason").alias("explicit_anchor_reason"),
        "selected_baseline_level",
        "fallback_depth",
        F.col("selected_population_size").alias("population_size"),
        F.col("selected_support_count").alias("support_count"),
        F.col("selected_prevalence").alias("prevalence"),
        strength.alias("expectation_evidence_strength"),
        F.lit(config.method_id).alias("expected_access_method_id"),
        F.lit(config.version).alias("expected_access_method_version"),
        "hard_trusted_rule_version",
        "baseline_version",
        "fallback_version",
        "source_snapshot_id",
        "baseline_source_snapshot_id",
        "baseline_timestamp",
        F.current_timestamp().alias("evaluated_at"),
    )


def _decision_columns(config, *, invalid_analytical_data, no_baseline):
    blocked = F.col("data_quality_blocking")
    anchor = F.coalesce(F.col("hard_trusted_flag"), F.lit(False))
    status = (
        F.when(blocked | invalid_analytical_data, INSUFFICIENT_EVIDENCE)
        .when(anchor, EXPECTED)
        .when(no_baseline, INSUFFICIENT_EVIDENCE)
        .when(
            F.col("selected_prevalence") >= config.expected_prevalence_threshold,
            EXPECTED,
        )
        .when(
            F.col("selected_prevalence") <= config.unexpected_prevalence_threshold,
            UNEXPECTED,
        )
        .otherwise(INSUFFICIENT_EVIDENCE)
    )
    reason = (
        F.when(blocked, "INSUFFICIENT_ANALYTICAL_DATA_BLOCKED")
        .when(invalid_analytical_data, "INSUFFICIENT_ANALYTICAL_DATA")
        .when(anchor, "EXPECTED_EXPLICIT_BIRTHRIGHT")
        .when(no_baseline, "INSUFFICIENT_NO_BASELINE")
        .when(
            F.col("selected_prevalence") >= config.expected_prevalence_threshold,
            "EXPECTED_HIGH_CONTEXT_PREVALENCE",
        )
        .when(
            F.col("selected_prevalence") <= config.unexpected_prevalence_threshold,
            "UNEXPECTED_LOW_CONTEXT_PREVALENCE",
        )
        .otherwise("INSUFFICIENT_AMBIGUOUS_PREVALENCE")
    )
    return status, reason


def _validate_one_to_one_contract(hts: DataFrame, fallback: DataFrame) -> None:
    keys = ["grant_id", "assessment_date"]
    for frame, name in ((hts, "Hard Trusted Set"), (fallback, "Hierarchical Fallback")):
        if (
            frame.where(F.col("grant_id").isNull() | F.col("assessment_date").isNull())
            .limit(1)
            .count()
        ):
            raise ValueError(f"{name} contains a null grant/date key")
        if frame.groupBy(*keys).count().where("count > 1").limit(1).count():
            raise ValueError(f"{name} violates one-row-per-grant/date grain")
    hts_keys = hts.select(*keys)
    fallback_keys = fallback.select(*keys)
    if (
        hts_keys.join(fallback_keys, keys, "left_anti").limit(1).count()
        or fallback_keys.join(hts_keys, keys, "left_anti").limit(1).count()
    ):
        raise ValueError("HTS and fallback grant/date keys are not a one-to-one match")


def _validate_versions_and_time(
    fallback: DataFrame, config: ExpectedAccessConfig
) -> None:
    if (
        fallback.where(
            F.col("baseline_version").isNull()
            | (F.col("baseline_version") != config.supported_baseline_version)
        )
        .limit(1)
        .count()
    ):
        raise ValueError("Unsupported baseline_version for Expected Access")
    if (
        fallback.where(
            F.col("fallback_version").isNull()
            | (F.col("fallback_version") != config.supported_fallback_version)
        )
        .limit(1)
        .count()
    ):
        raise ValueError("Unsupported fallback_version for Expected Access")
    if (
        fallback.where(F.to_date("baseline_timestamp") > F.col("assessment_date"))
        .limit(1)
        .count()
    ):
        raise ValueError("Future baseline_timestamp cannot influence Expected Access")


def _require_columns(frame: DataFrame, required: set[str], name: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{name} missing Expected Access fields: {sorted(missing)}")
