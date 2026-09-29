"""Evaluate PD001 over immutable EV001 grant-level evidence bundles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from .contract import CLASSIFICATIONS, PolicyDecisionConfig, RuleConfig

KEYS = ["grant_id", "assessment_date"]
REQUIRED_SUMMARY = frozenset({
    *KEYS, "evidence_bundle_id", "evidence_bundle_method_id", "evidence_bundle_version",
    "evidence_ids", "access_context_source_snapshot_id", "data_quality_blocking",
    "explicit_anchor_flag", "expected_access_status", "expectation_evidence_strength",
    "approval_relevance", "approval_linkage_quality", "approval_effective_at",
    "certification_decision", "certification_date", "certification_campaign_id",
    "public_application", "certification_pending_count", "inherited_access_candidate",
    "identity_history_complete", "no_usage_recorded", "usage_coverage",
    "contradiction_codes",
})


@dataclass(frozen=True)
class PolicyOutputs:
    decisions: DataFrame


def build_policy_decisions(
    evidence_summary: DataFrame,
    config: PolicyDecisionConfig,
    *,
    decision_run_id: str = "pd001-dry-run",
    decided_at: datetime | None = None,
) -> PolicyOutputs:
    """Return one deterministic PD001 decision per EV001 bundle.

    The evaluator intentionally reads only EV001's already-aggregated summary:
    it cannot reopen upstream 1:N approval or certification joins.
    """
    _validate_input(evidence_summary, config)
    timestamp = (decided_at or datetime.now(UTC)).replace(tzinfo=None)
    rules = {rule.rule_id: rule for rule in config.rules}
    frame = _conditions(evidence_summary, rules)
    candidates = ["R001", "R010", "R015", "R020", "R030", "R040", "R110"]
    winner = F.coalesce(*[F.when(F.col(f"_match_{rule}"), F.lit(rule)) for rule in candidates])
    frame = frame.withColumn("_winning_rule_id", winner)
    rule_map = F.create_map(*[item for rule in config.rules for item in (F.lit(rule.rule_id), F.lit(rule.reason_code))])
    class_map = F.create_map(*[item for rule in config.rules if rule.classification for item in (F.lit(rule.rule_id), F.lit(rule.classification))])
    source_map = F.create_map(*[item for rule in config.rules for item in (F.lit(rule.rule_id), F.lit(rule.policy_source))])
    version_map = F.create_map(*[item for rule in config.rules for item in (F.lit(rule.rule_id), F.lit(rule.rule_version))])
    supporting = F.sort_array(F.array_distinct(F.array_compact(F.array(*[
        F.when(F.col(f"_match_{rule}"), F.lit(rules[rule].reason_code))
        for rule in ("R041", "R060", "R065", "R066", "R070", "R080", "R090", "R100")
    ]))))
    evaluated = F.array(*[_trace(rule.rule_id, rule) for rule in config.rules])
    decisions = frame.select(
        *KEYS,
        F.lit(config.policy_id).alias("policy_id"), F.lit(config.version).alias("policy_version"),
        F.element_at(class_map, F.col("_winning_rule_id")).alias("classification"),
        F.col("_winning_rule_id").alias("winning_rule_id"),
        F.element_at(version_map, F.col("_winning_rule_id")).alias("winning_rule_version"),
        F.element_at(source_map, F.col("_winning_rule_id")).alias("policy_source"),
        F.element_at(rule_map, F.col("_winning_rule_id")).alias("primary_reason_code"),
        supporting.alias("supporting_reason_codes"),
        F.sort_array(F.array_distinct(F.array_compact(F.array(*[
            F.when(F.col(f"_match_{rule}"), F.lit(rule)) for rule in rules
        ])))).alias("applied_rule_ids"),
        F.col("evidence_ids").alias("evidence_ids"),
        F.when(F.col("_winning_rule_id").isin("R001", "R010", "R015", "R020", "R030", "R040"), F.col("evidence_ids"))
        .otherwise(F.array().cast("array<string>")).alias("decisive_evidence_ids"),
        _missing_evidence().alias("missing_evidence"),
        F.coalesce(F.col("contradiction_codes"), F.array().cast("array<string>")).alias("contradiction_codes"),
        F.col("evidence_bundle_id"), F.col("access_context_source_snapshot_id").alias("source_snapshot_id"),
        evaluated.alias("decision_trace"), F.lit(timestamp).cast("timestamp").alias("decision_timestamp"),
        F.lit(decision_run_id).alias("decision_run_id"),
    )
    _validate_output(decisions)
    return PolicyOutputs(decisions=decisions)


def _conditions(frame: DataFrame, rules: dict[str, RuleConfig]) -> DataFrame:
    enabled = lambda key: F.lit(rules[key].enabled)
    dated_certification = F.col("certification_date").isNotNull() & F.col("certification_campaign_id").isNotNull() & (F.col("certification_date") <= F.col("assessment_date"))
    direct_approval = F.col("approval_linkage_quality").startswith("DIRECT")
    return frame.select(
        "*",
        (enabled("R001") & F.coalesce(F.col("data_quality_blocking"), F.lit(False))).alias("_match_R001"),
        F.lit(False).alias("_match_R010"),  # catalog is disabled until bank policy is supplied
        (enabled("R015") & (F.col("certification_decision") == "REVOKE") & dated_certification).alias("_match_R015"),
        (enabled("R020") & F.coalesce(F.col("explicit_anchor_flag"), F.lit(False))).alias("_match_R020"),
        (enabled("R030") & ~F.coalesce(F.col("explicit_anchor_flag"), F.lit(False)) & (F.col("expected_access_status") == "EXPECTED") & (F.col("expectation_evidence_strength") == "HIGH")).alias("_match_R030"),
        (enabled("R040") & (F.col("approval_relevance") == "CONFIRMED") & direct_approval & F.col("approval_effective_at").isNotNull() & (F.col("approval_effective_at") <= F.col("assessment_date"))).alias("_match_R040"),
        (enabled("R041") & (F.col("approval_relevance") == "UNCERTAIN") & (F.col("approval_linkage_quality") == "STRONG_INFERRED")).alias("_match_R041"),
        (enabled("R060") & F.coalesce(F.col("public_application"), F.lit(False))).alias("_match_R060"),
        (enabled("R065") & (F.col("certification_decision") == "MAINTAIN") & dated_certification).alias("_match_R065"),
        (enabled("R066") & (F.coalesce(F.col("certification_pending_count"), F.lit(0)) > 0)).alias("_match_R066"),
        (enabled("R070") & F.coalesce(F.col("inherited_access_candidate"), F.lit(False)) & ~F.coalesce(F.col("identity_history_complete"), F.lit(False))).alias("_match_R070"),
        (enabled("R080") & (F.coalesce(F.col("no_usage_recorded"), F.lit(False)) | (F.col("usage_coverage") == "UNKNOWN"))).alias("_match_R080"),
        (enabled("R090") & (F.col("expected_access_status") == "UNEXPECTED")).alias("_match_R090"),
        (enabled("R100") & (F.col("expected_access_status") == "INSUFFICIENT_EVIDENCE")).alias("_match_R100"),
        enabled("R110").alias("_match_R110"),
    )


def _trace(rule: str, config: RuleConfig):
    return F.struct(
        F.lit(rule).alias("rule_id"), F.lit(config.rule_version).alias("rule_version"), F.lit(config.priority).alias("priority"),
        F.lit(config.rule_type).alias("rule_type"), F.lit(config.policy_source).alias("policy_source"),
        F.when(F.col(f"_match_{rule}"), "TRUE").otherwise("FALSE").alias("condition_result"),
        F.col(f"_match_{rule}").alias("matched"), F.lit("PERTINENT").alias("temporal_status"),
    )


def _missing_evidence():
    return F.sort_array(F.array_compact(F.array(
        F.when(F.col("approval_relevance").isNull() | (F.col("approval_relevance") == "NOT_FOUND"), "APPROVAL_NOT_CONFIRMED"),
        F.when(F.col("expected_access_status") == "INSUFFICIENT_EVIDENCE", "ANALYTICAL_EXPECTATION_INSUFFICIENT"),
        F.when(F.col("usage_coverage") == "UNKNOWN", "USAGE_COVERAGE_UNKNOWN"),
    )))


def _validate_input(frame: DataFrame, config: PolicyDecisionConfig) -> None:
    missing = REQUIRED_SUMMARY - set(frame.columns)
    if missing:
        raise ValueError(f"Evidence summary missing PD001 fields: {sorted(missing)}")
    if frame.where(F.col("grant_id").isNull() | F.col("assessment_date").isNull()).limit(1).count() or frame.groupBy(*KEYS).count().where("count > 1").limit(1).count():
        raise ValueError("Evidence summary violates one-row-per-grant/date grain")
    for column, expected in (("evidence_bundle_method_id", config.supported_evidence_method_id), ("evidence_bundle_version", config.supported_evidence_version)):
        if frame.where(F.col(column).isNull() | (F.col(column) != expected)).limit(1).count():
            raise ValueError(f"Unsupported {column} for PD001")
    future = (F.col("approval_effective_at") > F.col("assessment_date")) | (F.col("certification_date") > F.col("assessment_date"))
    if frame.where(future).limit(1).count():
        raise ValueError("Future evidence cannot enter PD001")


def _validate_output(frame: DataFrame) -> None:
    if frame.where(~F.col("classification").isin(*CLASSIFICATIONS) | F.col("winning_rule_id").isNull()).limit(1).count():
        raise ValueError("PD001 failed to select exactly one valid terminal decision")
