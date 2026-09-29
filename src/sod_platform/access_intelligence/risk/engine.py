"""RISK001 deterministic operational prioritization over frozen Policy/Evidence."""

from __future__ import annotations

from pathlib import Path

import yaml
from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

KEYS = ("grant_id", "assessment_date")
FORBIDDEN = {"scenario", "cenario", "ground_truth", "classificacao_esperada", "expected_class"}
POLICY_REQUIRED = set(KEYS) | {"policy_decision", "policy_rule_id", "policy_reason_code", "policy_version"}
EVIDENCE_REQUIRED = set(KEYS) | {
    "evidence_bundle_method_id", "evidence_bundle_version", "approval_evidence_status",
    "approval_linkage_quality", "certification_status", "data_quality_blocking",
    "contradiction_codes", "application_criticality", "entitlement_privileged",
    "data_classification", "regulatory_scope", "identidade_id", "entitlement_id",
}
CONTEXT_REQUIRED = set(KEYS) | {
    "criticidade", "classificacao_dado", "regulatory_scope", "privileged",
}
COMPONENTS = (
    "decision_risk_component", "privileged_risk_component", "criticality_risk_component",
    "regulatory_risk_component", "data_classification_risk_component",
    "evidence_risk_component", "temporal_risk_component",
)


def _invalid(message: str) -> ValueError:
    return ValueError(f"RISK001_CONFIG_INVALID: {message}")


def load_risk_config(path: Path) -> dict:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise _invalid("root must be a mapping")
    required = {"id", "version", "dataset_version", "policy_version", "evidence_method_id",
                "evidence_version", "score_max", "policy", "privileged", "criticality",
                "regulatory_scope", "data_classification", "evidence", "temporal", "bands",
                "monitor_impact_min", "driver_codes"}
    if required - config.keys():
        raise _invalid(f"missing keys: {sorted(required - config.keys())}")
    if (config["id"], config["version"], config["dataset_version"], config["policy_version"],
        config["evidence_method_id"], config["evidence_version"]) != (
        "RISK001", "1.0.0", "V2", "PD002/1.0.1", "EV001", "1.3.1"
    ):
        raise _invalid("unsupported input or method version")
    if config["score_max"] != 100 or type(config["score_max"]) is not int:
        raise _invalid("score_max must be 100")
    for name, keys in {
        "policy": {"INDEVIDO", "REVISAO", "LEGITIMO", "PADRAO"},
        "privileged": {True, False},
        "criticality": {"CRITICAL", "HIGH", "LOW"},
        "regulatory_scope": {"BACEN", "SOX", "NONE"},
        "data_classification": {"RESTRICTED", "CONFIDENTIAL", "INTERNAL", "PUBLIC"},
        "evidence": {"revoke_contradiction", "blocking_data_quality", "ambiguous_authorization"},
        "temporal": {"default"},
    }.items():
        values = config[name]
        if not isinstance(values, dict) or set(values) != keys:
            raise _invalid(f"{name} domain must equal {sorted(map(str, keys))}")
        if any(type(weight) is not int or weight < 0 or weight > 100 for weight in values.values()):
            raise _invalid(f"{name} weights must be integers in 0..100")
    if (max(config["policy"].values()) <= max(config["privileged"].values()) or
        max(config["policy"].values()) <= max(config["criticality"].values())):
        raise _invalid("policy must be the largest component")
    maximum = (max(config[name].values()) for name in
               ("policy", "privileged", "criticality", "regulatory_scope", "data_classification", "evidence"))
    if sum(maximum) + config["temporal"]["default"] > config["score_max"]:
        raise _invalid("component maximum exceeds score_max")
    if config["temporal"]["default"] != 0:
        raise _invalid("temporal component is zero in RISK001 1.0.0")
    bands = config["bands"]
    if not isinstance(bands, dict) or list(bands) != ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
        raise _invalid("bands must define LOW, MEDIUM, HIGH, CRITICAL in order")
    expected_start = 0
    for name, bounds in bands.items():
        if (not isinstance(bounds, list) or len(bounds) != 2 or
            any(type(v) is not int for v in bounds) or bounds[0] != expected_start or
            bounds[1] < bounds[0]):
            raise _invalid(f"overlapping or missing band at {name}")
        expected_start = bounds[1] + 1
    if expected_start != 101:
        raise _invalid("bands must cover 0..100")
    if type(config["monitor_impact_min"]) is not int or not 0 <= config["monitor_impact_min"] <= 100:
        raise _invalid("monitor_impact_min must be in 0..100")
    drivers = config["driver_codes"]
    if not isinstance(drivers, dict) or set(drivers) != {
        "policy", "privileged", "criticality", "regulatory", "data_classification", "evidence"
    } or set(drivers["policy"]) != {"INDEVIDO", "REVISAO", "LEGITIMO"}:
        raise _invalid("driver_codes incomplete")
    return config


def band_for_score(score: int, config: dict) -> str:
    for band, (low, high) in config["bands"].items():
        if low <= score <= high:
            return band
    raise ValueError(f"RISK001_SCORE_OUT_OF_RANGE: {score}")


def _map(column: str, values: dict):
    return F.create_map(*[part for key, weight in values.items()
                           for part in (F.lit(key), F.lit(weight))])[F.col(column)]


def _unique(frame: DataFrame, label: str) -> None:
    missing = set(KEYS) - set(frame.columns)
    if missing or frame.where(F.col("grant_id").isNull() | F.col("assessment_date").isNull()).limit(1).count():
        raise ValueError(f"RISK001_INVALID_GRAIN: {label}")
    if frame.groupBy(*KEYS).count().where("count > 1").limit(1).count():
        raise ValueError(f"RISK001_DUPLICATE_KEY: {label}")


def build_risk_assessment(policy: DataFrame, evidence: DataFrame,
                          context: DataFrame, config: dict) -> DataFrame:
    for label, frame, required in (
        ("Policy", policy, POLICY_REQUIRED), ("Evidence", evidence, EVIDENCE_REQUIRED),
        ("Access Context", context, CONTEXT_REQUIRED),
    ):
        missing = required - set(frame.columns)
        if missing or FORBIDDEN.intersection(frame.columns):
            raise ValueError(f"RISK001_INVALID_SCHEMA: {label}; missing={sorted(missing)}")
        _unique(frame, label)
    if policy.where(F.col("policy_version") != config["policy_version"]).limit(1).count():
        raise ValueError("RISK001_INPUT_VERSION: Policy")
    if evidence.where((F.col("evidence_bundle_method_id") != config["evidence_method_id"]) |
                      (F.col("evidence_bundle_version") != config["evidence_version"])).limit(1).count():
        raise ValueError("RISK001_INPUT_VERSION: Evidence")
    e = evidence.select(*KEYS, "identidade_id", "entitlement_id", "approval_evidence_status",
                        "approval_linkage_quality", "certification_status", "data_quality_blocking",
                        "contradiction_codes", "application_criticality", "entitlement_privileged",
                        "data_classification", F.col("regulatory_scope").alias("e_regulatory_scope"))
    c = context.select(*KEYS, F.col("criticidade").alias("physical_criticality"),
                       F.col("classificacao_dado").alias("physical_data_classification"),
                       F.col("regulatory_scope").alias("physical_regulatory_scope"),
                       F.col("privileged").alias("physical_privileged"))
    frame = policy.select(*KEYS, "policy_decision", "policy_rule_id", "policy_reason_code",
                          "policy_version").join(e, list(KEYS)).join(c, list(KEYS)).cache()
    if frame.count() != policy.count() or frame.count() != evidence.count() or frame.count() != context.count():
        raise ValueError("RISK001_JOIN_LOSS")
    if frame.where(~F.col("application_criticality").eqNullSafe(F.col("physical_criticality")) |
                   ~F.col("data_classification").eqNullSafe(F.col("physical_data_classification")) |
                   ~F.col("e_regulatory_scope").eqNullSafe(F.col("physical_regulatory_scope")) |
                   ~F.col("entitlement_privileged").eqNullSafe(F.col("physical_privileged"))).limit(1).count():
        raise ValueError("RISK001_CONTEXT_EVIDENCE_MISMATCH")
    for column, values in (
        ("policy_decision", config["policy"]), ("entitlement_privileged", config["privileged"]),
        ("application_criticality", config["criticality"]),
        ("e_regulatory_scope", config["regulatory_scope"]),
        ("data_classification", config["data_classification"]),
    ):
        if frame.where(F.col(column).isNull() | ~F.col(column).isin(*values)).limit(1).count():
            raise ValueError(f"UNMAPPED_RISK_VALUE: {column}")
    components = frame.select(
        "*",
        _map("policy_decision", config["policy"]).alias("decision_risk_component"),
        _map("entitlement_privileged", config["privileged"]).alias("privileged_risk_component"),
        _map("application_criticality", config["criticality"]).alias("criticality_risk_component"),
        _map("e_regulatory_scope", config["regulatory_scope"]).alias("regulatory_risk_component"),
        _map("data_classification", config["data_classification"]).alias("data_classification_risk_component"),
        F.when(F.col("data_quality_blocking") == True, config["evidence"]["blocking_data_quality"])
         .when(F.col("certification_status") == "REVOKE", config["evidence"]["revoke_contradiction"])
         .when(F.col("approval_evidence_status").isin("MULTIPLE_CANDIDATES", "TEMPORAL_CONFLICT", "INVALID_REQUEST_DATA"),
               config["evidence"]["ambiguous_authorization"])
         .otherwise(0).alias("evidence_risk_component"),
        F.lit(config["temporal"]["default"]).alias("temporal_risk_component"),
    )
    components = components.withColumn("impact_score", sum(F.col(n) for n in COMPONENTS[1:5]))
    components = components.withColumn("decision_severity_score", F.col("decision_risk_component"))
    components = components.withColumn("risk_score", F.least(F.lit(config["score_max"]), sum(F.col(n) for n in COMPONENTS)))
    band = F.coalesce(*[F.when(F.col("risk_score").between(low, high), F.lit(name))
                        for name, (low, high) in config["bands"].items()])
    components = components.withColumn("risk_band", band)
    action = (F.when(F.col("policy_decision") == "INDEVIDO", "REMEDIATE")
              .when(F.col("policy_decision") == "REVISAO", "REVIEW")
              .when(F.col("impact_score") >= config["monitor_impact_min"], "MONITOR")
              .otherwise("NONE"))
    components = components.withColumn("priority_action", action)
    components = components.withColumn(
        "priority_level",
        F.when(F.col("priority_action").isin("REMEDIATE", "REVIEW"),
               F.concat_ws("_", F.col("risk_band"), F.col("priority_action")))
         .when(F.col("priority_action") == "MONITOR", "SENSITIVITY_MONITOR")
         .otherwise("NO_ACTION"),
    )
    codes = config["driver_codes"]
    driver_columns = [
        ("decision_risk_component", F.coalesce(_map("policy_decision", codes["policy"]), F.lit(""))),
        ("privileged_risk_component", F.lit(codes["privileged"])),
        ("criticality_risk_component", F.lit(codes["criticality"])),
        ("regulatory_risk_component", F.lit(codes["regulatory"])),
        ("data_classification_risk_component", F.lit(codes["data_classification"])),
        ("evidence_risk_component", F.lit(codes["evidence"])),
    ]
    ranked = F.array_sort(F.array(*[
        F.struct((-F.col(component)).alias("negative_score"), F.lit(i).alias("order"), code.alias("code"))
        for i, (component, code) in enumerate(driver_columns)
    ]))
    components = components.withColumn("_ranked_drivers", F.filter(ranked, lambda item: item.negative_score < 0))
    for i in range(1, 4):
        components = components.withColumn(f"risk_driver_{i}", F.get(F.col("_ranked_drivers"), i - 1).code)
    window = Window.partitionBy("policy_decision").orderBy(F.col("risk_score").desc(), F.col("grant_id").asc())
    components = components.withColumn("priority_rank", F.row_number().over(window))
    return components.select(
        *KEYS, "identidade_id", "entitlement_id", "policy_decision", "policy_rule_id",
        "policy_reason_code", "policy_version", "risk_score", "risk_band", "priority_rank",
        "priority_level", "priority_action", "decision_severity_score", "impact_score",
        *COMPONENTS, "risk_driver_1", "risk_driver_2", "risk_driver_3",
        F.col("entitlement_privileged").alias("privileged"),
        F.col("application_criticality").alias("criticidade"),
        F.col("e_regulatory_scope").alias("regulatory_scope"),
        F.col("data_classification").alias("classificacao_dado"),
        "certification_status", "approval_evidence_status", "approval_linkage_quality",
        "data_quality_blocking", "contradiction_codes",
        F.lit("RISK001/1.0.0").alias("risk_version"),
    )
