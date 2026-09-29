"""PDISC002: global NMF + global HDBSCAN, strictly shadow-only.

This module deliberately has no dependency on Expected Access decisions or on
the validation fixture.  Spark prepares and persists relational data; the
guarded sparse matrix is the only artefact collected by the driver.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import (
    ArrayType,
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)
from pyspark.sql.window import Window
from scipy.sparse import csr_matrix
from sklearn.cluster import HDBSCAN
from sklearn.decomposition import NMF
from sklearn.preprocessing import normalize

from .engine import _reject_leakage


@dataclass(frozen=True)
class NmfHdbscanConfig:
    method_id: str
    version: str
    seed: int
    components: tuple[int, ...]
    max_iter: int
    l2_normalize: bool
    max_sparse_bytes: int
    min_cluster_size: int
    min_samples: int | None
    metric: str
    cluster_selection_method: str
    cluster_selection_epsilon: float
    min_peer_population: int
    min_support: int
    expected_threshold: float

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(self.__dict__, sort_keys=True).encode()
        ).hexdigest()


def load_nmf_hdbscan_config(path: Path) -> NmfHdbscanConfig:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))[
            "nmf_hdbscan_peer_discovery"
        ]
        nmf, hdb, base = value["nmf"], value["hdbscan"], value["peer_baseline"]
        config = NmfHdbscanConfig(
            str(value["method_id"]),
            str(value["version"]),
            int(nmf["seed"]),
            tuple(int(x) for x in nmf["components_candidates"]),
            int(nmf["max_iter"]),
            bool(value["normalization"].get("l2", True)),
            int(value["safety"]["max_sparse_bytes"]),
            int(hdb["min_cluster_size"]),
            int(hdb["min_samples"]) if hdb.get("min_samples") is not None else None,
            str(hdb["metric"]),
            str(hdb["cluster_selection_method"]),
            float(hdb.get("cluster_selection_epsilon", 0.0)),
            int(base["min_peer_population"]),
            int(base["min_support_count"]),
            float(base["expected_prevalence_threshold"]),
        )
    except (KeyError, TypeError, ValueError, OSError, yaml.YAMLError) as exc:
        raise ValueError(
            f"Invalid nmf_hdbscan_peer_discovery configuration: {exc}"
        ) from exc
    if not config.components or min(config.components) < 2:
        raise ValueError("components_candidates must contain integers >= 2")
    return config


def build_nmf_features(context: DataFrame) -> tuple[DataFrame, DataFrame, DataFrame]:
    """Make a deterministic, birthright-excluded feature dictionary in Spark."""
    _reject_leakage(context)
    needed = {
        "assessment_date",
        "identidade_id",
        "entitlement_id",
        "birthright",
        "data_quality_blocking",
        "status_identidade",
        "data_concessao",
    }
    missing = needed - set(context.columns)
    if missing:
        raise ValueError(f"Access Context missing NMF peer fields: {sorted(missing)}")
    valid = context.where(
        (~F.coalesce("data_quality_blocking", F.lit(True)))
        & (F.lower("status_identidade") == "active")
        & F.col("identidade_id").isNotNull()
        & F.col("entitlement_id").isNotNull()
        & (F.col("data_concessao") <= F.col("assessment_date"))
    )
    observed = (
        valid.where(~F.coalesce("birthright", F.lit(False)))
        .select("assessment_date", "identidade_id", "entitlement_id")
        .distinct()
    )
    dictionary = (
        observed.select("entitlement_id")
        .distinct()
        .withColumn(
            "feature_index",
            (F.row_number().over(Window.orderBy("entitlement_id")) - 1).cast("long"),
        )
    )
    identities = valid.select("assessment_date", "identidade_id").distinct()
    return observed.join(dictionary, "entitlement_id"), dictionary, identities


def _sparse_matrix(
    indexed: DataFrame,
    dictionary: DataFrame,
    identities: DataFrame,
    config: NmfHdbscanConfig,
):
    """Collect only index triples after an explicit driver-memory gate."""
    id_rows = identities.orderBy("assessment_date", "identidade_id").collect()
    feature_count = dictionary.count()
    nonzero_count = indexed.count()
    identity_count = len(id_rows)
    # CSR buffers: data float64 + column index int32 + row indptr int32.
    estimated = nonzero_count * 12 + (identity_count + 1) * 4
    metrics = {
        "identity_count": identity_count,
        "feature_count": feature_count,
        "nonzero_count": nonzero_count,
        "density": (
            (nonzero_count / (identity_count * feature_count))
            if identity_count and feature_count
            else 0.0
        ),
        "estimated_sparse_memory": estimated,
    }
    if estimated > config.max_sparse_bytes:
        raise RuntimeError("GLOBAL_MODEL_MEMORY_SAFETY_BLOCK")
    if not identity_count or not feature_count:
        return id_rows, csr_matrix((identity_count, feature_count)), metrics
    id_index = {
        (r["assessment_date"], r["identidade_id"]): i for i, r in enumerate(id_rows)
    }
    triples = (
        indexed.select("assessment_date", "identidade_id", "feature_index")
        .orderBy("assessment_date", "identidade_id", "feature_index")
        .collect()
    )
    rows = np.fromiter(
        (id_index[(r["assessment_date"], r["identidade_id"])] for r in triples),
        dtype=np.int32,
    )
    cols = np.fromiter((r["feature_index"] for r in triples), dtype=np.int32)
    return (
        id_rows,
        csr_matrix(
            (np.ones(len(triples)), (rows, cols)), shape=(identity_count, feature_count)
        ),
        metrics,
    )


def _fit(matrix: csr_matrix, config: NmfHdbscanConfig):
    viable = [k for k in config.components if k <= min(matrix.shape)]
    if not viable:
        raise ValueError("No NMF component candidate fits matrix dimensions")
    candidates, fitted = [], []
    for k in viable:
        model = NMF(
            n_components=k,
            init="nndsvda",
            random_state=config.seed,
            max_iter=config.max_iter,
        )
        weights = model.fit_transform(matrix)
        # Reconstruction error is an unsupervised, frozen selection criterion.
        candidates.append(
            {
                "n_components": k,
                "reconstruction_error": float(model.reconstruction_err_),
            }
        )
        fitted.append((k, model, weights))
    selected = min(
        range(len(candidates)),
        key=lambda i: (
            candidates[i]["reconstruction_error"],
            candidates[i]["n_components"],
        ),
    )
    return fitted[selected], candidates


def run_nmf_hdbscan(context: DataFrame, config: NmfHdbscanConfig) -> dict:
    """Run one global model and return shadow tables; never a classification."""
    started = time.monotonic()
    indexed, dictionary, identities = build_nmf_features(context)
    feature_started = time.monotonic()
    eligible_identities = indexed.select("assessment_date", "identidade_id").distinct()
    id_rows, matrix, memory = _sparse_matrix(
        indexed, dictionary, eligible_identities, config
    )
    sparse_seconds = time.monotonic() - feature_started
    no_features = {
        (r["assessment_date"], r["identidade_id"])
        for r in identities.select("assessment_date", "identidade_id").collect()
    } - {
        (r["assessment_date"], r["identidade_id"])
        for r in eligible_identities.collect()
    }
    if matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise RuntimeError("GLOBAL_MODEL_NO_ELIGIBLE_FEATURES")
    (k, model, vectors), candidates = _fit(matrix, config)
    nmf_seconds = time.monotonic() - started - sparse_seconds
    clustering_input = normalize(vectors, norm="l2") if config.l2_normalize else vectors
    hdb_started = time.monotonic()
    clusterer = HDBSCAN(
        min_cluster_size=config.min_cluster_size,
        min_samples=config.min_samples,
        metric=config.metric,
        cluster_selection_method=config.cluster_selection_method,
        cluster_selection_epsilon=config.cluster_selection_epsilon,
        allow_single_cluster=False,
    ).fit(clustering_input)
    hdb_seconds = time.monotonic() - hdb_started
    labels, probabilities = (
        clusterer.labels_,
        getattr(clusterer, "probabilities_", np.zeros(len(id_rows))),
    )
    outliers = getattr(clusterer, "outlier_scores_", np.full(len(id_rows), np.nan))
    members: dict[int, list[str]] = {}
    for row, label in zip(id_rows, labels):
        if label >= 0:
            members.setdefault(int(label), []).append(row["identidade_id"])
    stable = {
        label: f"{config.method_id}_{hashlib.sha256((config.config_hash + '|' + '|'.join(sorted(names))).encode()).hexdigest()[:16]}"
        for label, names in members.items()
    }
    records = []
    for row, vector, label, probability, outlier in zip(
        id_rows, vectors, labels, probabilities, outliers
    ):
        size = len(members.get(int(label), [])) if label >= 0 else 0
        status = (
            "NOISE"
            if label < 0
            else (
                "RELIABLE" if size >= config.min_peer_population else "LOW_CONFIDENCE"
            )
        )
        records.append(
            (
                row["identidade_id"],
                row["assessment_date"],
                stable.get(int(label)),
                int(label),
                float(probability),
                None if np.isnan(outlier) else float(outlier),
                status,
                [float(x) for x in vector],
                int(np.argmax(vector)),
                float(np.max(vector)),
                float(np.linalg.norm(vector)),
                size,
                config.version,
            )
        )
    schema = StructType(
        [
            StructField("identidade_id", StringType()),
            StructField("assessment_date", context.schema["assessment_date"].dataType),
            StructField("peer_group_id", StringType()),
            StructField("hdbscan_cluster_id", IntegerType()),
            StructField("membership_probability", DoubleType()),
            StructField("outlier_score", DoubleType()),
            StructField("peer_status", StringType()),
            StructField("nmf_vector", ArrayType(DoubleType())),
            StructField("dominant_component", IntegerType()),
            StructField("dominant_component_weight", DoubleType()),
            StructField("vector_norm", DoubleType()),
            StructField("cluster_size", IntegerType()),
            StructField("model_version", StringType()),
        ]
    )
    assignments = context.sparkSession.createDataFrame(records, schema)
    # Include abstentions explicitly, without inventing a model vector.
    abstention = [
        (
            identity,
            day,
            None,
            None,
            None,
            None,
            "NO_MODEL_FEATURES",
            None,
            None,
            None,
            None,
            0,
            config.version,
        )
        for day, identity in no_features
    ]
    if abstention:
        assignments = assignments.unionByName(
            context.sparkSession.createDataFrame(abstention, schema)
        )
    dictionary = dictionary.withColumn(
        "feature_dictionary_version", F.lit(config.config_hash)
    ).withColumn("model_version", F.lit(config.version))
    components = [
        (
            i,
            [
                r["entitlement_id"]
                for r in dictionary.orderBy("feature_index").collect()
            ],
            [float(x) for x in model.components_[i]],
            config.version,
        )
        for i in range(k)
    ]
    component_schema = "component_id int, entitlement_ids array<string>, weights array<double>, model_version string"
    component_frame = context.sparkSession.createDataFrame(components, component_schema)
    baseline, shadow = peer_baseline_shadow(context, assignments, config)
    metrics = {
        "model_frozen": "NMF_HDBSCAN MODEL FROZEN FOR OFFLINE EVALUATION",
        "selected_n_components": k,
        "nmf_candidates": candidates,
        "memory": memory,
        "implementation": "sklearn.cluster.HDBSCAN",
        "feature_build_seconds": round(sparse_seconds, 3),
        "nmf_seconds": round(nmf_seconds, 3),
        "hdbscan_seconds": round(hdb_seconds, 3),
        "total_seconds": round(time.monotonic() - started, 3),
    }
    return {
        "feature_dictionary": dictionary,
        "components": component_frame,
        "identity_vectors": assignments,
        "assignments": assignments.select(
            "identidade_id",
            "assessment_date",
            "peer_group_id",
            "hdbscan_cluster_id",
            "membership_probability",
            "outlier_score",
            "peer_status",
            "cluster_size",
            "model_version",
        ),
        "baseline": baseline,
        "shadow": shadow,
        "metrics": metrics,
    }


def peer_baseline_shadow(
    context: DataFrame, assignments: DataFrame, config: NmfHdbscanConfig
) -> tuple[DataFrame, DataFrame]:
    reliable = assignments.where("peer_status = 'RELIABLE'")
    population = reliable.groupBy("assessment_date", "peer_group_id").agg(
        F.countDistinct("identidade_id").alias("population_size")
    )
    support = (
        context.select("assessment_date", "identidade_id", "entitlement_id")
        .distinct()
        .join(
            reliable.select("assessment_date", "identidade_id", "peer_group_id"),
            ["assessment_date", "identidade_id"],
        )
        .groupBy("assessment_date", "peer_group_id", "entitlement_id")
        .agg(F.countDistinct("identidade_id").alias("support_count"))
    )
    baseline = (
        support.join(population, ["assessment_date", "peer_group_id"])
        .withColumn("prevalence", F.col("support_count") / F.col("population_size"))
        .withColumn(
            "baseline_reliable",
            (F.col("population_size") >= config.min_peer_population)
            & (F.col("support_count") >= config.min_support),
        )
        .withColumn("model_version", F.lit(config.version))
    )
    grants = context.select(
        "grant_id", "assessment_date", "identidade_id", "entitlement_id"
    ).dropDuplicates(["grant_id", "assessment_date"])
    shadow = (
        grants.join(
            assignments.select(
                "assessment_date",
                "identidade_id",
                "peer_group_id",
                "peer_status",
                "cluster_size",
            ),
            ["assessment_date", "identidade_id"],
            "left",
        )
        .join(
            baseline.select(
                "assessment_date",
                "peer_group_id",
                "entitlement_id",
                "population_size",
                "support_count",
                "prevalence",
                "baseline_reliable",
            ),
            ["assessment_date", "peer_group_id", "entitlement_id"],
            "left",
        )
        .withColumn(
            "peer_expected_status",
            F.when(F.col("peer_status") == "NO_MODEL_FEATURES", "NO_MODEL_FEATURES")
            .when(F.col("peer_status") != "RELIABLE", "NO_RELIABLE_PEER")
            .when(
                ~F.coalesce("baseline_reliable", F.lit(False)),
                "NMF_HDBSCAN_PEER_INSUFFICIENT",
            )
            .when(
                F.col("prevalence") >= config.expected_threshold,
                "NMF_HDBSCAN_PEER_EXPECTED",
            )
            .otherwise("NMF_HDBSCAN_PEER_UNEXPECTED"),
        )
        .withColumn("model_version", F.lit(config.version))
    )
    return baseline, shadow
