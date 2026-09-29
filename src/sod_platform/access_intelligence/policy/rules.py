"""PD002: deterministic decisions over frozen EV001 1.3.1 bundles."""

from __future__ import annotations

from pathlib import Path

import yaml
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

KEYS = ("grant_id", "assessment_date")
FORBIDDEN = {"cenario", "classificacao_esperada", "ground_truth", "expected_class"}
REQUIRED = set(KEYS) | {
    "evidence_bundle_method_id", "evidence_bundle_version", "evidence_ids",
    "data_quality_blocking", "community_relation", "public_application",
    "birthright", "explicit_anchor_flag", "approval_evidence_status",
    "approval_linkage_quality", "request_source_coverage", "certification_status",
    "expected_access_status", "expectation_evidence_strength", "population_size",
    "support_count", "prevalence", "selected_baseline_level", "baseline_version",
    "contradiction_codes", "approval_effective_at", "certification_date",
}


def load_catalog(path: Path) -> dict:
    catalog = yaml.safe_load(path.read_text(encoding="utf-8"))
    if catalog["policy_id"] != "PD002" or catalog["version"] not in {"1.0.0", "1.0.1"}:
        raise ValueError("Unsupported PD002 catalog")
    ids = [rule["id"] for rule in catalog["rules"]]
    expected = ["R010", "R025", "R020", "R030", "R040", "R140", "R050", "R060", "R070", "R080", "R110", "R120", "R130", "R999"] if catalog["version"] == "1.0.0" else ["R010", "R025", "R020", "R030", "R040", "R140", "R050", "R060", "R070", "R080", "R130", "R110", "R120", "R999"]
    if ids != expected or len(set(ids)) != len(ids):
        raise ValueError("Invalid PD002 rule precedence")
    if any(rule["decision"] not in {"PADRAO", "LEGITIMO", "INDEVIDO", "REVISAO"} for rule in catalog["rules"]):
        raise ValueError("Invalid PD002 decision")
    return catalog


def build_pd002(summary: DataFrame, catalog: dict) -> DataFrame:
    missing = REQUIRED - set(summary.columns)
    if missing or FORBIDDEN.intersection(summary.columns):
        raise ValueError(f"Invalid evidence schema: missing={sorted(missing)}, forbidden={sorted(FORBIDDEN.intersection(summary.columns))}")
    if summary.where(F.col("grant_id").isNull() | F.col("assessment_date").isNull()).limit(1).count():
        raise ValueError("Null decision key")
    if summary.groupBy(*KEYS).count().where("count > 1").limit(1).count():
        raise ValueError("Duplicate evidence key")
    if summary.where((F.col("evidence_bundle_method_id") != catalog["evidence_method_id"]) | (F.col("evidence_bundle_version") != catalog["evidence_version"])).limit(1).count():
        raise ValueError("Unsupported Evidence version")
    if summary.where((F.col("approval_effective_at") > F.col("assessment_date")) | (F.col("certification_date") > F.col("assessment_date"))).limit(1).count():
        raise ValueError("Future evidence")
    cross = (F.col("community_relation") == "CROSS_COMMUNITY") & (F.col("public_application") == F.lit(False))
    strong = (F.col("approval_linkage_quality") == "STRONG_INFERRED") & (F.col("approval_evidence_status") == "UNIQUE_MATCH")
    missing_approval = F.col("approval_evidence_status") == "NOT_FOUND"
    revoke = F.col("certification_status") == "REVOKE"
    authoritative = F.col("request_source_coverage") == catalog["request_source_coverage"]
    expected = F.col("expected_access_status") == "EXPECTED"
    reliable = (F.col("expectation_evidence_strength") == "HIGH") & F.col("selected_baseline_level").isNotNull() & (F.col("population_size") > 0) & (F.col("support_count") > 0) & F.col("prevalence").isNotNull() & F.col("baseline_version").isNotNull()
    conditions = {
        "R010": F.col("data_quality_blocking") == True,
        "R025": cross & strong & revoke,
        "R020": cross & strong,
        "R030": cross & missing_approval & authoritative,
        "R040": revoke,
        "R140": ((F.col("approval_evidence_status") == "AMBIGUOUS") | (F.col("approval_relevance") == "UNCERTAIN")) if catalog["version"] == "1.0.0" else F.col("approval_evidence_status").isin("MULTIPLE_CANDIDATES", "TEMPORAL_CONFLICT", "INVALID_REQUEST_DATA"),
        "R050": F.col("explicit_anchor_flag") == True,
        "R060": (F.col("birthright") == False) & expected & reliable & ((F.col("community_relation") == "SAME_COMMUNITY") | (F.col("public_application") == True)),
        "R070": strong,
        "R080": (F.col("public_application") == True) & (F.col("explicit_anchor_flag") == False),
        "R110": F.col("expected_access_status") == "UNEXPECTED",
        "R120": F.col("expected_access_status") == "INSUFFICIENT_EVIDENCE",
        "R130": cross & missing_approval & ~authoritative,
        "R999": F.lit(True),
    }
    winner = F.coalesce(*[F.when(F.coalesce(conditions[rule["id"]], F.lit(False)), F.lit(rule["id"])) for rule in catalog["rules"]])
    decision_map = F.create_map(*[x for r in catalog["rules"] for x in (F.lit(r["id"]), F.lit(r["decision"]))])
    reason_map = F.create_map(*[x for r in catalog["rules"] for x in (F.lit(r["id"]), F.lit(r["reason"]))])
    frame = summary.withColumn("policy_rule_id", winner)
    return frame.select(
        *KEYS, F.element_at(decision_map, F.col("policy_rule_id")).alias("policy_decision"),
        F.element_at(reason_map, F.col("policy_rule_id")).alias("policy_reason_code"),
        "policy_rule_id", F.lit(f"PD002/{catalog['version']}").alias("policy_version"),
        F.col("expected_access_status").alias("expected_access_state"),
        F.col("expectation_evidence_strength").alias("expected_access_strength"),
        "community_relation", F.col("public_application").alias("sigla_publica"),
        "birthright", F.col("explicit_anchor_flag").alias("trusted_birthright"),
        "approval_evidence_status", F.col("approval_linkage_quality").alias("approval_match_strength"),
        "request_source_coverage", "certification_status", "data_quality_blocking",
        F.when(F.element_at(decision_map, F.col("policy_rule_id")) == "REVISAO", "LOW")
         .when(F.col("policy_rule_id") == "R080", "MEDIUM").otherwise("HIGH").alias("decision_confidence"),
        "evidence_bundle_id", "evidence_ids", "contradiction_codes", "selected_baseline_level",
        "population_size", "support_count", "prevalence", "baseline_version",
    )
