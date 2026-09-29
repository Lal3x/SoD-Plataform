"""Build EV001 evidence facts and a one-row-per-grant evidence summary.

This module normalizes facts. It deliberately contains no policy assessment,
risk, priority, impact, suspicion, or final-outcome logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from .contract import (
    ACCESS_CONTEXT_OPTIONAL,
    ACCESS_CONTEXT_REQUIRED,
    EXPECTED_ACCESS_REQUIRED,
    EvidenceEngineConfig,
)
from .reliability import (
    approval_reliability,
    certification_reliability,
    coverage_reliability,
    direct_reliability,
    expected_access_reliability,
    inherited_reliability,
)

KEYS = ["grant_id", "assessment_date"]
APPROVAL_VALUES = ("CONFIRMED", "UNCERTAIN", "NOT_FOUND")
EXPECTED_VALUES = ("EXPECTED", "UNEXPECTED", "INSUFFICIENT_EVIDENCE")
STRENGTH_VALUES = ("HIGH", "MEDIUM", "LOW")
USAGE_COVERAGE_VALUES = ("COMPLETE", "PARTIAL", "UNKNOWN")


@dataclass(frozen=True)
class EvidenceOutputs:
    summary: DataFrame
    facts: DataFrame


def build_evidence(
    access_context: DataFrame,
    expected_access: DataFrame,
    config: EvidenceEngineConfig,
    *,
    evaluated_at: datetime | None = None,
    requests: DataFrame | None = None,
    request_source_coverage: str | None = None,
) -> EvidenceOutputs:
    """Validate the 1:1 handoff and create deterministic EV001 outputs."""
    _require_columns(access_context, ACCESS_CONTEXT_REQUIRED, "Access Context")
    _require_columns(expected_access, EXPECTED_ACCESS_REQUIRED, "Expected Access")
    access_context = _with_optional_context_columns(access_context)
    if requests is not None:
        access_context = _match_requests(access_context, requests)
    else:
        access_context = access_context.withColumn("approval_candidate_count", F.lit(None).cast("long"))
        access_context = access_context.withColumn("approval_evidence_status", F.when(F.col("approval_linkage_quality") == "STRONG_INFERRED", "UNIQUE_MATCH").when(F.col("approval_linkage_quality") == "AMBIGUOUS", "MULTIPLE_CANDIDATES").otherwise("NOT_FOUND"))
    access_context = access_context.withColumn("request_source_coverage", F.lit(request_source_coverage).cast("string"))
    access_context = access_context.withColumn(
        "certification_status",
        F.coalesce(
            F.col("certification_decisao"),
            F.when(F.col("certification_pending_count") > 0, F.lit("PENDING")),
            F.lit("CERTIFICATION_NOT_FOUND"),
        ),
    )
    _validate_one_to_one(access_context, expected_access)
    _validate_domains_versions_and_time(access_context, expected_access, config)

    timestamp = (evaluated_at or datetime.now(UTC)).replace(tzinfo=None)
    # All fact branches derive from the same validated 1:1 frame. Persisting
    # this compact grant-level handoff prevents Spark from independently
    # planning the shared join once per evidence type.
    joined = (
        _join_inputs(access_context, expected_access)
        .withColumn("_evidence_evaluated_at", F.lit(timestamp).cast("timestamp"))
        .cache()
    )
    raw_facts = _build_facts(joined, config).cache()
    summary = _build_summary(joined, raw_facts, config)
    facts = raw_facts.join(
        summary.select(*KEYS, "evidence_bundle_id"), KEYS, "inner"
    ).select(
        "evidence_id",
        *KEYS,
        "evidence_category",
        "evidence_type",
        "evidence_value",
        "evidence_value_type",
        "evidence_attributes",
        "evidence_reliability",
        "reliability_reason_code",
        "observed_at",
        "effective_at",
        "temporal_status",
        "evidence_source_layer",
        "evidence_source_table",
        "source_snapshot_id",
        "source_record_id",
        "method_id",
        "method_version",
        "evidence_bundle_id",
        "evidence_bundle_method_id",
        "evidence_bundle_version",
        "evaluated_at",
    )
    return EvidenceOutputs(summary=summary, facts=facts)


def _join_inputs(context: DataFrame, expected: DataFrame) -> DataFrame:
    context_columns = [
        F.col(f"c.{name}")
        for name in sorted(
            (ACCESS_CONTEXT_REQUIRED | set(ACCESS_CONTEXT_OPTIONAL) | {"approval_candidate_count", "approval_evidence_status", "request_source_coverage", "certification_status"}) - set(KEYS)
        )
    ]
    expected_columns = [
        F.col(f"e.{name}").alias(
            "expected_source_snapshot_id" if name == "source_snapshot_id" else name
        )
        for name in sorted(EXPECTED_ACCESS_REQUIRED - set(KEYS))
    ]
    return context.alias("c").join(expected.alias("e"), KEYS, "inner").select(
        *[F.col(name) for name in KEYS], *context_columns, *expected_columns
    )


def _match_requests(context: DataFrame, requests: DataFrame) -> DataFrame:
    """Describe observable request candidates without asserting a causal FK."""
    required = {"identidade_id", "entitlement_id", "request_id", "status_solicitacao",
                "data_solicitacao", "data_aprovacao", "aprovador"}
    _require_columns(requests, frozenset(required), "Requests")
    pair = ["identidade_id", "entitlement_id"]
    relevant = requests.where(F.col("status_solicitacao") == "APPROVED")
    relevant = relevant.select(*pair, "request_id", "data_solicitacao", "data_aprovacao", "aprovador")
    joined = context.select(*KEYS, *pair, "data_concessao").join(relevant, pair, "left")
    observed = F.col("request_id").isNotNull()
    coherent = (observed & F.col("data_solicitacao").isNotNull()
                & F.col("data_aprovacao").isNotNull() & F.col("aprovador").isNotNull()
                & (F.col("data_solicitacao") <= F.col("data_aprovacao"))
                & (F.col("data_aprovacao") <= F.col("data_concessao"))
                & (F.col("data_aprovacao") <= F.col("assessment_date")))
    stats = joined.groupBy(*KEYS).agg(
        F.count("request_id").alias("_request_count"),
        F.sum(F.when(coherent, 1).otherwise(0)).alias("approval_candidate_count"),
    )
    status = (F.when(F.col("_request_count") == 0, "NOT_FOUND")
              .when(F.col("approval_candidate_count") > 1, "MULTIPLE_CANDIDATES")
              .when(F.col("_request_count") > F.col("approval_candidate_count"), "TEMPORAL_CONFLICT")
              .when(F.col("approval_candidate_count") == 1, "UNIQUE_MATCH")
              .otherwise("INVALID_REQUEST_DATA"))
    stats = stats.withColumn("approval_evidence_status", status).drop("_request_count")
    result = context.join(stats, KEYS, "left")
    return (result.withColumn("approval_linkage_quality",
            F.when(F.col("approval_evidence_status") == "UNIQUE_MATCH", "STRONG_INFERRED")
             .when(F.col("approval_evidence_status") == "MULTIPLE_CANDIDATES", "AMBIGUOUS")
             .otherwise("UNKNOWN"))
        .withColumn("approval_relevance",
            F.when(F.col("approval_evidence_status").isin("UNIQUE_MATCH", "MULTIPLE_CANDIDATES", "TEMPORAL_CONFLICT"), "UNCERTAIN")
             .otherwise("NOT_FOUND")))


def _build_facts(frame: DataFrame, config: EvidenceEngineConfig) -> DataFrame:
    boolean = lambda name: _boolean_value(F.col(name))
    facts = [
        _fact(
            frame,
            config,
            category="EXPLICIT_CONTEXT",
            evidence_type="BIRTHRIGHT",
            value=boolean("birthright"),
            value_type="BOOLEAN",
            reliability=direct_reliability(F.col("birthright")),
            reliability_reason=_direct_reason(F.col("birthright")),
            source_table="sod.silver.access_context",
            source_record_id=F.col("entitlement_id"),
            effective_at=F.col("assessment_date").cast("timestamp"),
        ),
        _fact(frame, config, category="EXPLICIT_CONTEXT", evidence_type="TRUSTED_BIRTHRIGHT",
              value=boolean("explicit_anchor_flag"), value_type="BOOLEAN",
              reliability=direct_reliability(F.col("explicit_anchor_flag")),
              reliability_reason=F.col("explicit_anchor_reason"),
              source_table="sod.access_intelligence.expected_access", source_record_id=F.col("grant_id"),
              effective_at=F.col("assessment_date").cast("timestamp")),
        *[
            _fact(
                frame,
                config,
                category="EXPLICIT_CONTEXT",
                evidence_type=evidence_type,
                value=F.col(column),
                value_type="STRING",
                reliability=direct_reliability(F.col(column)),
                reliability_reason=_direct_reason(F.col(column)),
                source_table="sod.silver.access_context",
                source_record_id=F.col(source_record),
                effective_at=F.col("assessment_date").cast("timestamp"),
            )
            for evidence_type, column, source_record in (
                ("IDENTITY_TYPE", "tipo_identidade", "identidade_id"),
                ("IDENTITY_COMMUNITY", "comunidade", "identidade_id"),
                ("IDENTITY_SQUAD", "squad", "identidade_id"),
                ("IDENTITY_ROLE", "cargo", "identidade_id"),
                ("ENTITLEMENT_OWNER_COMMUNITY", "comunidade_dona_sigla", "entitlement_id"),
            )
        ],
        _fact(
            frame,
            config,
            category="EXPLICIT_CONTEXT",
            evidence_type="PUBLIC_APPLICATION",
            value=boolean("sigla_publica"),
            value_type="BOOLEAN",
            reliability=direct_reliability(F.col("sigla_publica")),
            reliability_reason=_direct_reason(F.col("sigla_publica")),
            source_table="sod.silver.access_context",
            source_record_id=F.col("sigla_id"),
            effective_at=F.col("assessment_date").cast("timestamp"),
        ),
        _fact(
            frame,
            config,
            category="EXPLICIT_CONTEXT",
            evidence_type="COMMUNITY_RELATION",
            value=(
                F.when(F.col("cross_community").isNull(), "UNKNOWN")
                .when(F.col("cross_community"), "CROSS_COMMUNITY")
                .otherwise("SAME_COMMUNITY")
            ),
            value_type="STRING",
            reliability=direct_reliability(F.col("cross_community")),
            reliability_reason=_direct_reason(F.col("cross_community")),
            source_table="sod.silver.access_context",
            source_record_id=F.col("grant_id"),
            effective_at=F.col("assessment_date").cast("timestamp"),
        ),
        _fact(
            frame,
            config,
            category="AUTHORIZATION",
            evidence_type="APPROVAL_RELEVANCE",
            value=F.col("approval_relevance"),
            value_type="STRING",
            reliability=approval_reliability(
                F.col("approval_relevance"), F.col("approval_linkage_quality")
            ),
            reliability_reason=(
                F.when(F.col("approval_relevance") == "CONFIRMED", "DIRECT_LINK_UPSTREAM")
                .when(
                    (F.col("approval_relevance") == "UNCERTAIN")
                    & (F.col("approval_linkage_quality") == "STRONG_INFERRED"),
                    "STRONG_INFERRED_LINKAGE",
                )
                .when(F.col("approval_relevance") == "UNCERTAIN", "INFERRED_LINKAGE")
                .otherwise("DOCUMENT_COVERAGE_UNKNOWN")
            ),
            source_table="sod.silver.access_context",
            source_record_id=F.col("request_id"),
            effective_at=F.col("data_aprovacao").cast("timestamp"),
            attributes={
                "linkage_quality": F.col("approval_linkage_quality"),
                "candidate_count": F.col("approval_candidate_count"),
                "approval_to_grant_delta_days": F.col(
                    "approval_to_grant_delta_days"
                ),
            },
        ),
        _fact(frame, config, category="AUTHORIZATION", evidence_type="APPROVAL_EVIDENCE",
              value=F.col("approval_evidence_status"), value_type="STRING",
              reliability=approval_reliability(F.col("approval_relevance"), F.col("approval_linkage_quality")),
              reliability_reason=F.when(F.col("approval_evidence_status") == "UNIQUE_MATCH", "UNIQUE_COHERENT_INFERRED_MATCH").otherwise("NO_CAUSAL_LINK"),
              source_table="sod.silver.iga_access_requests", source_record_id=F.col("request_id"),
              effective_at=F.col("data_aprovacao").cast("timestamp"),
              attributes={"candidate_count": F.col("approval_candidate_count")}),
        _fact(frame, config, category="DATA_QUALITY", evidence_type="REQUEST_SOURCE_COVERAGE",
              value=F.col("request_source_coverage"), value_type="STRING",
              reliability=direct_reliability(F.col("request_source_coverage")),
              reliability_reason=_direct_reason(F.col("request_source_coverage")),
              source_table="sod.silver.iga_access_requests", source_record_id=F.lit(None).cast("string"),
              effective_at=F.col("assessment_date").cast("timestamp")),
        _fact(
            frame,
            config,
            category="AUTHORIZATION",
            evidence_type="CERTIFICATION_DECISION",
            value=F.col("certification_decisao"),
            value_type="STRING",
            reliability=certification_reliability(
                F.col("certification_decisao"),
                F.col("certification_data_revisao"),
                F.col("certification_campaign_id"),
            ),
            reliability_reason=F.when(
                F.col("certification_data_revisao").isNotNull()
                & F.col("certification_campaign_id").isNotNull(),
                "DATED_IDENTIFIED_CERTIFICATION",
            ).otherwise("CERTIFICATION_PROVENANCE_INCOMPLETE"),
            source_table="sod.silver.access_context",
            source_record_id=F.col("certification_campaign_id"),
            effective_at=F.col("certification_data_revisao").cast("timestamp"),
            where=(~F.col("certification_status").isin(
                "PENDING", "CERTIFICATION_NOT_FOUND"
            )),
        ),
        _fact(
            frame,
            config,
            category="AUTHORIZATION",
            evidence_type="CERTIFICATION_NOT_FOUND",
            value=F.lit("CERTIFICATION_NOT_FOUND"),
            value_type="STRING",
            reliability=F.lit("UNKNOWN"),
            reliability_reason=F.lit("NO_PERTINENT_CERTIFICATION_OBSERVED"),
            source_table="sod.silver.access_certifications",
            source_record_id=F.lit(None).cast("string"),
            effective_at=F.col("assessment_date").cast("timestamp"),
            where=F.col("certification_status") == "CERTIFICATION_NOT_FOUND",
        ),
        _fact(
            frame,
            config,
            category="AUTHORIZATION",
            evidence_type="CERTIFICATION_PENDING",
            value=F.lit("PENDING"),
            value_type="STRING",
            reliability=F.lit("LOW"),
            reliability_reason=F.lit("AGGREGATED_PENDING_WITHOUT_INDIVIDUAL_DATE"),
            source_table="sod.silver.access_context",
            source_record_id=F.lit(None).cast("string"),
            effective_at=F.lit(None).cast("timestamp"),
            where=F.col("certification_status") == "PENDING",
            attributes={"pending_count": F.col("certification_pending_count")},
        ),
        _fact(
            frame,
            config,
            category="ANALYTICAL_EXPECTATION",
            evidence_type="EXPECTED_ACCESS",
            value=F.col("expected_access_status"),
            value_type="STRING",
            reliability=expected_access_reliability(
                F.col("expected_access_status"), F.col("expectation_evidence_strength")
            ),
            reliability_reason=(
                F.when(
                    F.col("expected_access_status") == "INSUFFICIENT_EVIDENCE",
                    "ANALYTICAL_EVIDENCE_INSUFFICIENT",
                )
                .when(F.col("expectation_evidence_strength").isNotNull(), "CONTEXT_SPECIFICITY")
                .otherwise("ANALYTICAL_RELIABILITY_UNKNOWN")
            ),
            source_table="sod.access_intelligence.expected_access",
            source_record_id=F.lit(None).cast("string"),
            source_snapshot=F.sha2(
                F.concat_ws(
                    "|",
                    F.coalesce(F.col("expected_source_snapshot_id"), F.lit("<NULL>")),
                    F.coalesce(F.col("baseline_source_snapshot_id"), F.lit("<NULL>")),
                ),
                256,
            ),
            observed_at=F.col("evaluated_at"),
            effective_at=F.col("assessment_date").cast("timestamp"),
            attributes={
                "reason": F.col("expected_access_reason"),
                "strength": F.col("expectation_evidence_strength"),
                "baseline_level": F.col("selected_baseline_level"),
                "fallback_depth": F.col("fallback_depth"),
                "population_size": F.col("population_size"),
                "support_count": F.col("support_count"),
                "prevalence": F.col("prevalence"),
                "expected_access_method_id": F.col("expected_access_method_id"),
                "expected_access_method_version": F.col("expected_access_method_version"),
            },
        ),
        _fact(
            frame,
            config,
            category="TEMPORAL_USAGE",
            evidence_type="INHERITED_ACCESS_CANDIDATE",
            value=boolean("inherited_access_candidate"),
            value_type="BOOLEAN",
            reliability=inherited_reliability(
                F.col("inherited_access_candidate"), F.col("identity_history_complete")
            ),
            reliability_reason=(
                F.when(F.col("inherited_access_candidate").isNull(), "CANDIDATE_UNKNOWN")
                .when(~F.coalesce(F.col("identity_history_complete"), F.lit(False)), "IDENTITY_HISTORY_INCOMPLETE")
                .otherwise("IDENTITY_HISTORY_COMPLETE")
            ),
            source_table="sod.silver.access_context",
            source_record_id=F.col("grant_id"),
            effective_at=F.col("data_concessao").cast("timestamp"),
        ),
        _fact(frame, config, category="TEMPORAL_USAGE", evidence_type="GRANT_DATE",
              value=F.col("data_concessao").cast("string"), value_type="DATE",
              reliability=direct_reliability(F.col("data_concessao")),
              reliability_reason=_direct_reason(F.col("data_concessao")),
              source_table="sod.silver.access_context", source_record_id=F.col("grant_id"),
              effective_at=F.col("data_concessao").cast("timestamp")),
        _fact(frame, config, category="TEMPORAL_USAGE", evidence_type="GRANT_AGE_DAYS",
              value=F.col("access_age_days").cast("string"), value_type="LONG",
              reliability=direct_reliability(F.col("access_age_days")),
              reliability_reason=_direct_reason(F.col("access_age_days")),
              source_table="sod.silver.access_context", source_record_id=F.col("grant_id"),
              effective_at=F.col("assessment_date").cast("timestamp")),
        _fact(
            frame,
            config,
            category="TEMPORAL_USAGE",
            evidence_type="USAGE_OBSERVATION",
            value=(
                F.when(F.col("no_usage_recorded").isNull(), "UNKNOWN")
                .when(F.col("no_usage_recorded"), "NO_USAGE_RECORDED")
                .otherwise("USAGE_RECORDED")
            ),
            value_type="STRING",
            reliability=coverage_reliability(F.col("usage_coverage")),
            reliability_reason=F.concat(F.lit("USAGE_COVERAGE_"), F.coalesce(F.col("usage_coverage"), F.lit("UNKNOWN"))),
            source_table="sod.silver.access_context",
            source_record_id=F.col("grant_id"),
            effective_at=F.col("ultimo_uso").cast("timestamp"),
            attributes={
                "usage_coverage": F.col("usage_coverage"),
                "last_usage_at": F.col("ultimo_uso"),
                "days_since_last_use": F.col("days_since_last_use"),
            },
        ),
        _fact(
            frame,
            config,
            category="DATA_QUALITY",
            evidence_type="IDENTITY_HISTORY_COVERAGE",
            value=(
                F.when(F.col("identity_history_complete").isNull(), "UNKNOWN")
                .when(F.col("identity_history_complete"), "COMPLETE")
                .otherwise("INCOMPLETE")
            ),
            value_type="STRING",
            reliability=direct_reliability(F.col("identity_history_complete")),
            reliability_reason=_direct_reason(F.col("identity_history_complete")),
            source_table="sod.silver.access_context",
            source_record_id=F.col("identidade_id"),
            effective_at=F.col("assessment_date").cast("timestamp"),
        ),
        _fact(
            frame,
            config,
            category="DATA_QUALITY",
            evidence_type="USAGE_COVERAGE",
            value=F.coalesce(F.col("usage_coverage"), F.lit("UNKNOWN")),
            value_type="STRING",
            reliability=direct_reliability(F.col("usage_coverage")),
            reliability_reason=_direct_reason(F.col("usage_coverage")),
            source_table="sod.silver.access_context",
            source_record_id=F.col("grant_id"),
            effective_at=F.col("assessment_date").cast("timestamp"),
        ),
        _fact(
            frame,
            config,
            category="DATA_QUALITY",
            evidence_type="BLOCKING_DATA_QUALITY",
            value=boolean("data_quality_blocking"),
            value_type="BOOLEAN",
            reliability=direct_reliability(F.col("data_quality_blocking")),
            reliability_reason=_direct_reason(F.col("data_quality_blocking")),
            source_table="sod.silver.access_context",
            source_record_id=F.col("grant_id"),
            effective_at=F.col("assessment_date").cast("timestamp"),
        ),
    ]
    facts.extend(
        _sensitivity_fact(frame, config, evidence_type, column, source_record)
        for evidence_type, column, source_record in (
            ("PRIVILEGED_ACCESS", "entitlement_privileged", "entitlement_id"),
            ("APPLICATION_CRITICALITY", "application_criticality", "sigla_id"),
            ("DATA_CLASSIFICATION", "classificacao_dado", "entitlement_id"),
            ("REGULATORY_SCOPE", "regulatory_scope", "entitlement_id"),
        )
    )
    output = facts[0]
    for fact in facts[1:]:
        output = output.unionByName(fact)
    # Normalize partitioning after the heterogeneous fact branches. This keeps
    # later groupBy/join operations stable under Spark AQE and avoids carrying
    # incompatible child partitioning metadata into the summary plan.
    return output.repartition(*KEYS)


def _sensitivity_fact(frame, config, evidence_type, column, source_record):
    value = F.col(column)
    if column == "entitlement_privileged":
        rendered, value_type = _boolean_value(value), "BOOLEAN"
    else:
        rendered, value_type = value.cast("string"), "STRING"
    return _fact(
        frame,
        config,
        category="SENSITIVITY",
        evidence_type=evidence_type,
        value=rendered,
        value_type=value_type,
        reliability=direct_reliability(value),
        reliability_reason=_direct_reason(value),
        source_table="sod.silver.access_context",
        source_record_id=F.col(source_record),
        effective_at=F.col("assessment_date").cast("timestamp"),
    )


def _fact(
    frame: DataFrame,
    config: EvidenceEngineConfig,
    *,
    category: str,
    evidence_type: str,
    value: Column,
    value_type: str,
    reliability: Column,
    reliability_reason: Column,
    source_table: str,
    source_record_id: Column,
    effective_at: Column,
    attributes: dict[str, Column] | None = None,
    where: Column | None = None,
    source_snapshot: Column | None = None,
    observed_at: Column | None = None,
) -> DataFrame:
    attributes = attributes or {}
    attribute_map = F.create_map(
        *[
            item
            for key, expression in attributes.items()
            for item in (F.lit(key), expression.cast("string"))
        ]
    ) if attributes else F.from_json(F.lit("{}"), "map<string,string>")
    source_snapshot = source_snapshot if source_snapshot is not None else F.col("source_snapshot_id")
    observed_at = observed_at if observed_at is not None else F.col("_evidence_evaluated_at")
    temporal_status = F.when(effective_at.isNull(), "EFFECTIVE_TIME_UNKNOWN").otherwise("PERTINENT")
    base = frame if where is None else frame.where(where)
    selected = base.select(
        *KEYS,
        F.lit(category).alias("evidence_category"),
        F.lit(evidence_type).alias("evidence_type"),
        F.coalesce(value.cast("string"), F.lit("UNKNOWN")).alias("evidence_value"),
        F.lit(value_type).alias("evidence_value_type"),
        attribute_map.alias("evidence_attributes"),
        reliability.alias("evidence_reliability"),
        reliability_reason.alias("reliability_reason_code"),
        observed_at.cast("timestamp").alias("observed_at"),
        effective_at.cast("timestamp").alias("effective_at"),
        temporal_status.alias("temporal_status"),
        F.lit("SILVER" if source_table.startswith("sod.silver") else "ACCESS_INTELLIGENCE").alias("evidence_source_layer"),
        F.lit(source_table).alias("evidence_source_table"),
        source_snapshot.alias("source_snapshot_id"),
        source_record_id.cast("string").alias("source_record_id"),
        F.lit(config.method_id).alias("method_id"),
        F.lit(config.version).alias("method_version"),
        F.lit(config.method_id).alias("evidence_bundle_method_id"),
        F.lit(config.version).alias("evidence_bundle_version"),
        F.col("_evidence_evaluated_at").alias("evaluated_at"),
    )
    canonical = F.concat_ws(
        "|",
        *[
            F.coalesce(F.col(name).cast("string"), F.lit("<NULL>"))
            for name in (
                "grant_id",
                "assessment_date",
                "evidence_type",
                "evidence_value",
                "evidence_source_layer",
                "evidence_source_table",
                "source_snapshot_id",
                "source_record_id",
                "effective_at",
                "method_id",
                "method_version",
            )
        ],
    )
    return selected.withColumn("evidence_id", F.sha2(canonical, 256)).select(
        "evidence_id", *selected.columns
    )


def _build_summary(frame: DataFrame, facts: DataFrame, config: EvidenceEngineConfig) -> DataFrame:
    evidence = facts.groupBy(*KEYS).agg(
        F.sort_array(F.collect_set("evidence_id")).alias("evidence_ids"),
        F.count("evidence_id").alias("evidence_count"),
    )
    mixed = F.sort_array(
        F.array_compact(
            F.array(
                F.when(
                    (F.col("expected_access_status") == "UNEXPECTED")
                    & (F.col("approval_relevance") == "CONFIRMED"),
                    "MX001_UNEXPECTED_WITH_CONFIRMED_APPROVAL",
                ),
                F.when(
                    (F.col("expected_access_status") == "UNEXPECTED")
                    & (F.col("certification_decisao") == "MAINTAIN"),
                    "MX002_UNEXPECTED_WITH_MAINTAIN_CERTIFICATION",
                ),
                F.when(
                    F.col("sigla_publica")
                    & (F.col("expected_access_status") == "INSUFFICIENT_EVIDENCE"),
                    "MX003_PUBLIC_WITH_INSUFFICIENT_EXPECTATION",
                ),
                F.when(
                    F.col("inherited_access_candidate")
                    & (~F.coalesce(F.col("identity_history_complete"), F.lit(False))),
                    "MX004_INHERITED_CANDIDATE_WITH_INCOMPLETE_HISTORY",
                ),
            )
        )
    )
    contradictions = F.sort_array(
        F.array_compact(
            F.array(
                F.when(
                    F.col("explicit_anchor_flag")
                    & (F.col("certification_decisao") == "REVOKE"),
                    "CX001_BIRTHRIGHT_ANCHOR_WITH_REVOKE_CERTIFICATION",
                ),
                F.when(
                    (F.col("approval_relevance") == "CONFIRMED")
                    & (F.col("certification_decisao") == "REVOKE"),
                    "CX002_CONFIRMED_APPROVAL_WITH_REVOKE_CERTIFICATION",
                ),
                F.when(
                    (~F.coalesce(F.col("data_quality_blocking"), F.lit(True)))
                    & F.col("expected_access_reason").isin(
                        "INSUFFICIENT_ANALYTICAL_DATA",
                        "INSUFFICIENT_ANALYTICAL_DATA_BLOCKED",
                    ),
                    "CX003_CONTEXT_AND_ANALYTICAL_DQ_CONFLICT",
                ),
            )
        )
    )
    enriched = (
        frame.withColumn("mixed_evidence_codes", mixed)
        .withColumn("contradiction_codes", contradictions)
        .withColumn("mixed_evidence_flag", F.size("mixed_evidence_codes") > 0)
        .withColumn("contradictory_evidence_flag", F.size("contradiction_codes") > 0)
        .join(evidence, KEYS, "inner")
        .withColumn(
            "evidence_bundle_id",
            F.sha2(
                F.concat_ws(
                    "|",
                    F.col("grant_id"),
                    F.col("assessment_date").cast("string"),
                    F.lit(config.method_id),
                    F.lit(config.version),
                    F.array_join("evidence_ids", "|"),
                    F.array_join("mixed_evidence_codes", "|"),
                    F.array_join("contradiction_codes", "|"),
                ),
                256,
            ),
        )
    )
    return enriched.select(
        *KEYS,
        "identidade_id",
        F.col("tipo_identidade").alias("identity_type"),
        F.col("comunidade").alias("identity_community"),
        "squad",
        "cargo",
        "entitlement_id",
        "sigla_id",
        F.col("comunidade_dona_sigla").alias("owner_community"),
        "birthright",
        "explicit_anchor_flag",
        "explicit_anchor_reason",
        F.col("sigla_publica").alias("public_application"),
        F.when(F.col("cross_community").isNull(), "UNKNOWN")
        .when(F.col("cross_community"), "CROSS_COMMUNITY")
        .otherwise("SAME_COMMUNITY")
        .alias("community_relation"),
        "cross_community",
        "approval_relevance",
        "approval_linkage_quality",
        "approval_evidence_status",
        "approval_candidate_count",
        "request_source_coverage",
        F.col("request_id").alias("approval_request_id"),
        F.col("data_aprovacao").alias("approval_effective_at"),
        "certification_status",
        F.col("certification_decisao").alias("certification_decision"),
        F.col("certification_data_revisao").alias("certification_date"),
        F.col("certification_campaign_id"),
        "certification_pending_count",
        "expected_access_status",
        "expected_access_reason",
        "expectation_evidence_strength",
        "selected_baseline_level",
        "fallback_depth",
        "population_size",
        "support_count",
        "prevalence",
        "inherited_access_candidate",
        "identity_history_complete",
        "access_age_days",
        "no_usage_recorded",
        "usage_coverage",
        "ultimo_uso",
        "days_since_last_use",
        "entitlement_privileged",
        "application_criticality",
        F.col("classificacao_dado").alias("data_classification"),
        "regulatory_scope",
        "data_quality_blocking",
        "mixed_evidence_flag",
        "mixed_evidence_codes",
        "contradictory_evidence_flag",
        "contradiction_codes",
        "evidence_ids",
        "evidence_count",
        "evidence_bundle_id",
        F.lit(config.method_id).alias("evidence_bundle_method_id"),
        F.lit(config.version).alias("evidence_bundle_version"),
        F.col("source_snapshot_id").alias("access_context_source_snapshot_id"),
        "baseline_source_snapshot_id",
        F.col("_silver_run_id").alias("silver_run_id"),
        "expected_access_method_id",
        "expected_access_method_version",
        "hard_trusted_rule_version",
        "baseline_version",
        "fallback_version",
        "baseline_timestamp",
        F.col("_evidence_evaluated_at").alias("evaluated_at"),
    )


def _validate_one_to_one(context: DataFrame, expected: DataFrame) -> None:
    for frame, name in ((context, "Access Context"), (expected, "Expected Access")):
        if frame.where(F.col("grant_id").isNull() | F.col("assessment_date").isNull()).limit(1).count():
            raise ValueError(f"{name} contains a null grant/date key")
        if frame.groupBy(*KEYS).count().where("count > 1").limit(1).count():
            raise ValueError(f"{name} violates one-row-per-grant/date grain")
    context_keys, expected_keys = context.select(*KEYS), expected.select(*KEYS)
    if context_keys.join(expected_keys, KEYS, "left_anti").limit(1).count() or expected_keys.join(context_keys, KEYS, "left_anti").limit(1).count():
        raise ValueError("Access Context and Expected Access keys are not a one-to-one match")


def _validate_domains_versions_and_time(context, expected, config) -> None:
    version_checks = {
        "expected_access_method_id": config.supported_expected_access_method_id,
        "expected_access_method_version": config.supported_expected_access_method_version,
        "hard_trusted_rule_version": config.supported_hard_trusted_rule_version,
        "baseline_version": config.supported_baseline_version,
        "fallback_version": config.supported_fallback_version,
    }
    for column, supported in version_checks.items():
        if expected.where(F.col(column).isNull() | (F.col(column) != supported)).limit(1).count():
            raise ValueError(f"Unsupported {column} for Evidence Engine")
    domain_checks = (
        (context, "approval_relevance", APPROVAL_VALUES),
        (context, "usage_coverage", USAGE_COVERAGE_VALUES),
        (expected, "expected_access_status", EXPECTED_VALUES),
    )
    for frame, column, values in domain_checks:
        if frame.where(F.col(column).isNull() | (~F.col(column).isin(*values))).limit(1).count():
            raise ValueError(f"Invalid {column} for Evidence Engine")
    if expected.where(
        F.col("expectation_evidence_strength").isNotNull()
        & (~F.col("expectation_evidence_strength").isin(*STRENGTH_VALUES))
    ).limit(1).count():
        raise ValueError("Invalid expectation_evidence_strength for Evidence Engine")
    future_context = (
        (F.col("data_concessao") > F.col("assessment_date"))
        | (F.col("data_aprovacao") > F.col("assessment_date"))
        | (F.col("data_aprovacao") > F.col("data_concessao"))
        | (F.col("certification_data_revisao") > F.col("assessment_date"))
        | (F.col("ultimo_uso") > F.col("assessment_date"))
    )
    if context.where(future_context).limit(1).count():
        raise ValueError("Future or temporally incoherent context evidence")
    if expected.where(F.to_date("baseline_timestamp") > F.col("assessment_date")).limit(1).count():
        raise ValueError("Future baseline evidence cannot enter Evidence Engine")


def _require_columns(frame: DataFrame, required: frozenset[str], name: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{name} missing Evidence Engine fields: {sorted(missing)}")


def _with_optional_context_columns(frame: DataFrame) -> DataFrame:
    for name, data_type in ACCESS_CONTEXT_OPTIONAL.items():
        if name not in frame.columns:
            frame = frame.withColumn(name, F.lit(None).cast(data_type))
    return frame


def _boolean_value(value: str | Column) -> Column:
    column = F.col(value) if isinstance(value, str) else value
    return F.when(column.isNull(), "UNKNOWN").when(column, "TRUE").otherwise("FALSE")


def _direct_reason(value: Column) -> Column:
    return F.when(value.isNotNull(), "DIRECT_VALID_CONTEXT").otherwise("SOURCE_VALUE_UNKNOWN")
