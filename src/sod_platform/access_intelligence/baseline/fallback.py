"""Deterministically select a sufficiently supported observed baseline.

This module selects *which* comparable population can be used.  It never
labels a grant as expected, unexpected, legitimate, or inappropriate.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

FALLBACK_VERSION = "2.0.0"
REQUIRED_CONTEXT_COLUMNS = {
    "grant_id",
    "assessment_date",
    "entitlement_id",
    "comunidade",
    "squad",
    "cargo",
    "tipo_identidade",
}
REQUIRED_BASELINE_COLUMNS = {
    "assessment_date",
    "baseline_level",
    "comunidade",
    "squad",
    "cargo",
    "tipo_identidade",
    "entitlement_id",
    "population_size",
    "support_count",
    "prevalence",
    "baseline_version",
    "source_snapshot_id",
    "baseline_timestamp",
}
LEVELS = (
    (
        "SQUAD_CARGO_TIPO_IDENTIDADE",
        ("comunidade", "squad", "cargo", "tipo_identidade"),
    ),
    ("COMUNIDADE_CARGO", ("comunidade", "cargo")),
    ("COMUNIDADE", ("comunidade",)),
    ("POPULACAO_COMPARAVEL", ("tipo_identidade",)),
)


@dataclass(frozen=True)
class HierarchicalFallbackConfig:
    """Versioned technical support requirements for a POC baseline."""

    minimum_population_size: int
    minimum_support_count: int
    baseline_version: str
    version: str = FALLBACK_VERSION

    def __post_init__(self) -> None:
        if self.minimum_population_size < 1 or self.minimum_support_count < 1:
            raise ValueError("Minimum population and support must both be positive")
        if not self.baseline_version or not self.version:
            raise ValueError("Baseline and fallback versions must be non-empty")


def load_hierarchical_fallback_config(path: Path) -> HierarchicalFallbackConfig:
    """Load explicit, calibratable (not gabarito-derived) POC parameters."""
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        values = payload["hierarchical_fallback"]
        return HierarchicalFallbackConfig(
            minimum_population_size=int(values["minimum_population_size"]),
            minimum_support_count=int(values["minimum_support_count"]),
            baseline_version=str(values["baseline_version"]),
            version=str(values["version"]),
        )
    except (KeyError, OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        raise ValueError(
            f"Invalid hierarchical fallback configuration {path}: {exc}"
        ) from exc


def select_hierarchical_fallback(
    access_context: DataFrame,
    observed_baseline: DataFrame,
    config: HierarchicalFallbackConfig,
) -> DataFrame:
    """Return one explainable baseline-selection result for every context grant.

    Only baseline rows of the configured version and the exact assessment date
    can join.  Missing dimensions make an attempted level inapplicable rather
    than creating an artificial ``UNKNOWN`` population.
    """
    _require_columns(access_context, REQUIRED_CONTEXT_COLUMNS, "Access Context")
    _require_columns(observed_baseline, REQUIRED_BASELINE_COLUMNS, "Observed Baseline")

    result = access_context.select(*REQUIRED_CONTEXT_COLUMNS)
    candidates: list[dict[str, F.Column]] = []
    for index, (level, dimensions) in enumerate(LEVELS):
        baseline = observed_baseline.where(
            (F.col("baseline_level") == level)
            & (F.col("baseline_version") == config.baseline_version)
        ).alias(f"b{index}")
        conditions = [
            F.col("c.assessment_date") == F.col(f"b{index}.assessment_date"),
            F.col("c.entitlement_id") == F.col(f"b{index}.entitlement_id"),
        ]
        conditions.extend(
            F.col(f"c.{dimension}") == F.col(f"b{index}.{dimension}")
            for dimension in dimensions
        )
        condition = conditions[0]
        for extra in conditions[1:]:
            condition = condition & extra
        result = (
            result.alias("c")
            .join(baseline, condition, "left")
            .select(
                "c.*",
                F.col(f"b{index}.population_size").alias(f"population_{index}"),
                F.col(f"b{index}.support_count").alias(f"support_{index}"),
                F.col(f"b{index}.prevalence").alias(f"prevalence_{index}"),
                F.col(f"b{index}.source_snapshot_id").alias(f"snapshot_{index}"),
                F.col(f"b{index}.baseline_timestamp").alias(f"timestamp_{index}"),
            )
        )
        applicable = F.lit(True)
        for dimension in dimensions:
            applicable = applicable & F.col(dimension).isNotNull()
        present = F.col(f"population_{index}").isNotNull()
        sufficient = (
            applicable
            & present
            & (F.col(f"population_{index}") >= config.minimum_population_size)
            & (F.col(f"support_{index}") >= config.minimum_support_count)
        )
        reason = (
            F.when(~applicable, F.lit("MISSING_REQUIRED_DIMENSIONS"))
            .when(~present, F.lit("BASELINE_NOT_AVAILABLE"))
            .when(~sufficient, F.lit("INSUFFICIENT_ANALYTICAL_SUPPORT"))
            .otherwise(F.lit("SUFFICIENT"))
        )
        candidates.append({"sufficient": sufficient, "reason": reason})

    selected_index = F.lit(None).cast("int")
    for index in reversed(range(len(LEVELS))):
        selected_index = F.when(
            candidates[index]["sufficient"], F.lit(index)
        ).otherwise(selected_index)

    def selected_value(prefix: str, cast: str | None = None) -> F.Column:
        value = F.lit(None)
        for index in reversed(range(len(LEVELS))):
            value = F.when(
                selected_index == index, F.col(f"{prefix}_{index}")
            ).otherwise(value)
        return value.cast(cast) if cast else value

    attempts = F.array(
        *[
            F.concat(F.lit(f"{level}:"), candidates[index]["reason"])
            for index, (level, _) in enumerate(LEVELS)
        ]
    )
    selected_level = F.lit(None).cast("string")
    for index, (level, _) in reversed(list(enumerate(LEVELS))):
        selected_level = F.when(selected_index == index, F.lit(level)).otherwise(
            selected_level
        )

    return result.select(
        "grant_id",
        "assessment_date",
        selected_level.alias("selected_baseline_level"),
        selected_value("population", "long").alias("selected_population_size"),
        selected_value("support", "long").alias("selected_support_count"),
        selected_value("prevalence", "double").alias("selected_prevalence"),
        F.lit(config.baseline_version).alias("baseline_version"),
        selected_value("snapshot", "string").alias("baseline_source_snapshot_id"),
        selected_value("timestamp", "timestamp").alias("baseline_timestamp"),
        (selected_index > 0).alias("fallback_applied"),
        F.coalesce(selected_index, F.lit(len(LEVELS))).alias("fallback_depth"),
        (selected_index.isNotNull()).alias("baseline_sufficient"),
        F.when(selected_index.isNotNull(), F.lit("BASELINE_SELECTED"))
        .otherwise(F.lit("INSUFFICIENT_EVIDENCE"))
        .alias("selection_status"),
        F.concat_ws(";", attempts).alias("fallback_reason"),
        F.lit(config.version).alias("fallback_version"),
    )


def _require_columns(frame: DataFrame, required: set[str], name: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{name} missing fallback fields: {sorted(missing)}")
