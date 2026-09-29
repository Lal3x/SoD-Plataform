"""Spark-native peer discovery and shadow expectedness.

``cenario`` and ``classificacao_esperada`` are intentionally rejected at the
boundary: they are offline-evaluation metadata, never model input.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import yaml
from pyspark.ml.clustering import LDA
from pyspark.ml.fpm import FPGrowth
from pyspark.ml.functions import vector_to_array
from pyspark.ml.linalg import Vectors, VectorUDT
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window

FORBIDDEN_COLUMNS = {"cenario", "classificacao_esperada"}
PEER_BASELINE_NOT_RELIABLE = "PEER_BASELINE_NOT_RELIABLE"


@dataclass(frozen=True)
class PeerDiscoveryConfig:
    method_id: str
    version: str
    seed: int
    topics_candidates: tuple[int, ...]
    max_iter: int
    optimizer: str
    min_primary_weight: float
    min_top1_top2_gap: float
    max_entropy: float
    min_support: float
    min_confidence: float
    min_context_population: int
    baseline_version: str
    min_population: int
    min_baseline_support: int
    expected_prevalence_threshold: float
    exclude_birthright_features: bool = False

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.__dict__, sort_keys=True).encode()).hexdigest()


def load_peer_discovery_config(path: Path) -> PeerDiscoveryConfig:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))["peer_discovery"]
        lda, membership, fp, baseline = value["lda"], value["membership"], value["fp_growth"], value["peer_baseline"]
        features = value.get("features", {})
        config = PeerDiscoveryConfig(str(value["method_id"]), str(value["version"]), int(lda["seed"]), tuple(int(k) for k in lda["topics_candidates"]), int(lda["max_iter"]), str(lda["optimizer"]), float(membership["min_primary_weight"]), float(membership["min_top1_top2_gap"]), float(membership["max_entropy"]), float(fp["min_support"]), float(fp["min_confidence"]), int(fp["min_context_population"]), str(baseline["baseline_version"]), int(baseline["min_population"]), int(baseline["min_support"]), float(baseline["expected_prevalence_threshold"]), bool(features.get("exclude_birthright", True)))
    except (KeyError, TypeError, ValueError, OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Invalid peer_discovery configuration {path}: {exc}") from exc
    if not config.topics_candidates or any(k < 2 for k in config.topics_candidates):
        raise ValueError("topics_candidates must contain values >= 2")
    return config


def _reject_leakage(frame: DataFrame) -> None:
    found = FORBIDDEN_COLUMNS & set(frame.columns)
    if found:
        raise ValueError(f"Peer discovery rejects offline ground-truth columns: {sorted(found)}")


def build_sparse_features(context: DataFrame, config: PeerDiscoveryConfig) -> tuple[DataFrame, DataFrame, DataFrame]:
    """Return identity documents, deterministic entitlement dictionary, and valid grants."""
    _reject_leakage(context)
    required = {"identidade_id", "entitlement_id", "assessment_date", "data_quality_blocking", "status_identidade", "data_concessao"}
    missing = required - set(context.columns)
    if missing:
        raise ValueError(f"Access Context missing peer discovery fields: {sorted(missing)}")
    valid = context.where((~F.coalesce("data_quality_blocking", F.lit(True))) & (F.lower("status_identidade") == "active") & F.col("identidade_id").isNotNull() & F.col("entitlement_id").isNotNull() & (F.col("data_concessao") <= F.col("assessment_date")))
    feature_observations = valid
    if config.exclude_birthright_features:
        if "birthright" not in context.columns:
            raise ValueError("Access Context missing birthright required for peer feature exclusion")
        feature_observations = feature_observations.where(~F.coalesce("birthright", F.lit(False)))
    dictionary = feature_observations.select("entitlement_id").distinct().withColumn("feature_index", (F.row_number().over(Window.orderBy("entitlement_id")) - 1).cast("long"))
    indexed = feature_observations.join(dictionary, "entitlement_id").select("assessment_date", "identidade_id", "feature_index").distinct()
    size = dictionary.agg((F.max("feature_index") + 1).alias("size"))
    # The UDF receives only each distributed identity's sparse indices, never a dense matrix.
    make_vector = F.udf(lambda indices, n: Vectors.sparse(int(n), list(map(int, indices)), [1.0] * len(indices)), VectorUDT())
    documents = indexed.groupBy("assessment_date", "identidade_id").agg(F.sort_array(F.collect_set("feature_index")).alias("indices")).crossJoin(size).withColumn("features", make_vector("indices", "size")).drop("indices", "size")
    return documents, dictionary, valid


def _membership(frame: DataFrame, config: PeerDiscoveryConfig, topics: int) -> DataFrame:
    values = vector_to_array("role_vector")
    # Spark array functions retain this calculation distributed and make thresholds auditable.
    top1 = F.array_max(values)
    sorted_values = F.reverse(F.array_sort(values))
    top2 = F.element_at(sorted_values, 2)
    entropy = -F.aggregate(values, F.lit(0.0), lambda acc, x: acc + F.when(x > 0, x * F.log(x)).otherwise(F.lit(0.0))) / F.log(F.lit(float(topics)))
    confidence = (F.when((top1 >= config.min_primary_weight) & ((top1 - F.coalesce(top2, F.lit(0.0))) >= config.min_top1_top2_gap) & (entropy <= config.max_entropy), "HIGH_CONFIDENCE").when((top1 >= config.min_primary_weight) & (entropy <= 1.0), "MEDIUM_CONFIDENCE").when((top1 < config.min_primary_weight) | ((top1 - F.coalesce(top2, F.lit(0.0))) < config.min_top1_top2_gap), "AMBIGUOUS").otherwise("LOW_CONFIDENCE"))
    return frame.withColumn("role_array", values).withColumn("dominant_role", (F.array_position("role_array", top1) - 1).cast("int")).withColumn("dominant_role_weight", top1).withColumn("role_entropy", entropy).withColumn("peer_confidence", confidence).drop("role_array")


def run_peer_discovery(context: DataFrame, config: PeerDiscoveryConfig) -> dict[str, DataFrame | dict]:
    """Fit LDA, mine bundles, construct peer baseline and shadow statuses."""
    documents, dictionary, valid = build_sparse_features(context, config)
    candidate_metrics, models = [], []
    for k in config.topics_candidates:
        model = LDA(k=k, maxIter=config.max_iter, optimizer=config.optimizer, seed=config.seed, featuresCol="features", topicDistributionCol="role_vector").fit(documents)
        candidate_metrics.append((k, float(model.logLikelihood(documents)), float(model.logPerplexity(documents))))
        models.append((k, model))
    # Frozen unsupervised criterion: maximum log likelihood, then lower k for stability.
    selected_k, model = min(zip(candidate_metrics, models), key=lambda x: (-x[0][1], x[0][0]))[1]
    transformed = _membership(model.transform(documents), config, selected_k)
    context_columns = [c for c in ("comunidade", "squad", "cargo", "tipo_identidade") if c in valid.columns]
    identity_context = valid.select("assessment_date", "identidade_id", *context_columns).dropDuplicates(["assessment_date", "identidade_id"])
    assignments = transformed.join(identity_context, ["assessment_date", "identidade_id"], "left").withColumn("role_id", F.concat(F.lit("ROLE_"), F.lpad(F.col("dominant_role").cast("string"), 2, "0"))).withColumn("peer_group_id", F.sha2(F.concat_ws("|", *[F.coalesce(F.col(c), F.lit("UNKNOWN")) for c in [*context_columns, "role_id"]], F.lit(config.config_hash)), 256)).withColumn("model_version", F.lit(config.version)).withColumn("feature_dictionary_version", F.lit(config.config_hash)).withColumn("input_snapshot_id", F.lit(None).cast("string"))
    # Iceberg cannot persist Spark's VectorUDT.  Store the same topic
    # probabilities as a primitive array so the shadow assignment remains
    # physically auditable without changing the fitted model or membership.
    assignments = assignments.withColumn("role_vector", vector_to_array("role_vector")).select("identidade_id", "assessment_date", "peer_group_id", "role_id", "dominant_role", "dominant_role_weight", "role_entropy", "peer_confidence", "model_version", "feature_dictionary_version", "input_snapshot_id", *context_columns, "role_vector")
    topic_rows = model.describeTopics().select(F.col("topic").alias("dominant_role"), "termIndices", "termWeights").join(dictionary.select(F.col("feature_index").cast("int").alias("feature_index"), "entitlement_id"), F.array_contains(F.col("termIndices"), F.col("feature_index")), "left")
    role_profiles = topic_rows.groupBy("dominant_role").agg(F.sort_array(F.collect_list(F.struct("feature_index", "entitlement_id"))).alias("top_entitlements"), F.first("termWeights").alias("topic_weights")).join(assignments.groupBy("dominant_role").agg(F.count("*").alias("identity_count"), F.avg("dominant_role_weight").alias("mean_membership"), F.percentile_approx("dominant_role_weight", 0.5).alias("p50_membership"), F.percentile_approx("dominant_role_weight", 0.9).alias("p90_membership")), "dominant_role", "left").withColumn("role_id", F.concat(F.lit("ROLE_"), F.lpad(F.col("dominant_role").cast("string"), 2, "0"))).withColumn("model_version", F.lit(config.version))
    items = valid.groupBy("assessment_date", "identidade_id").agg(F.sort_array(F.collect_set("entitlement_id")).alias("items"))
    fp = FPGrowth(itemsCol="items", minSupport=config.min_support, minConfidence=config.min_confidence).fit(items)
    patterns, rules = fp.freqItemsets.withColumn("model_version", F.lit(config.version)), fp.associationRules.withColumn("model_version", F.lit(config.version))
    peer_eligible = assignments.where(F.col("peer_confidence").isin("HIGH_CONFIDENCE", "MEDIUM_CONFIDENCE"))
    peer_population = peer_eligible.groupBy("assessment_date", "peer_group_id").agg(F.countDistinct("identidade_id").alias("population_size"))
    supports = valid.select("assessment_date", "identidade_id", "entitlement_id").distinct().join(peer_eligible.select("assessment_date", "identidade_id", "peer_group_id"), ["assessment_date", "identidade_id"]).groupBy("assessment_date", "peer_group_id", "entitlement_id").agg(F.countDistinct("identidade_id").alias("support_count"))
    baseline = supports.join(peer_population, ["assessment_date", "peer_group_id"]).withColumn("prevalence", F.col("support_count") / F.col("population_size")).withColumn("peer_baseline_reliability", F.when((F.col("population_size") >= config.min_population) & (F.col("support_count") >= config.min_baseline_support), "RELIABLE").otherwise(PEER_BASELINE_NOT_RELIABLE)).withColumn("peer_model_version", F.lit(config.version)).withColumn("baseline_version", F.lit(config.baseline_version))
    grants = context.select("grant_id", "assessment_date", "identidade_id", "entitlement_id").dropDuplicates(["grant_id", "assessment_date"])
    shadow = grants.join(assignments.select("assessment_date", "identidade_id", "peer_group_id", "peer_confidence"), ["assessment_date", "identidade_id"], "left").join(baseline.select("assessment_date", "peer_group_id", "entitlement_id", "population_size", "support_count", "prevalence", "peer_baseline_reliability"), ["assessment_date", "peer_group_id", "entitlement_id"], "left").withColumn("peer_expected_status", F.when(F.col("peer_baseline_reliability") != "RELIABLE", "PEER_INSUFFICIENT_EVIDENCE").when(F.col("prevalence") >= config.expected_prevalence_threshold, "PEER_EXPECTED").otherwise("PEER_NOT_STRONGLY_OBSERVED")).withColumn("peer_expected_reason", F.when(F.col("peer_baseline_reliability") != "RELIABLE", PEER_BASELINE_NOT_RELIABLE).when(F.col("prevalence") >= config.expected_prevalence_threshold, "PEER_HIGH_OBSERVED_PREVALENCE_NOT_AUTHORIZATION").otherwise("PEER_PREVALENCE_BELOW_SHADOW_THRESHOLD")).withColumn("peer_model_version", F.lit(config.version)).withColumn("baseline_version", F.lit(config.baseline_version))
    return {"feature_dictionary": dictionary.withColumn("feature_dictionary_version", F.lit(config.config_hash)), "lda_assignments": assignments, "role_profiles": role_profiles, "frequent_patterns": patterns, "association_rules": rules, "peer_baseline": baseline, "peer_expected_shadow": shadow, "model_selection": {"selected_k": selected_k, "candidates": candidate_metrics}}
