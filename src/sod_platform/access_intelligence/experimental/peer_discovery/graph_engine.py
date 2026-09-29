"""Sparse, shadow-only graph peer discovery using Spark MinHash and Leiden.

Spark constructs and filters candidate edges; only the guarded reduced graph is
collected for local Leiden.  Ground-truth fields are rejected at this boundary.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from pyspark.ml.feature import MinHashLSH
from pyspark.ml.linalg import Vectors, VectorUDT
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType
from pyspark.sql.window import Window

from .engine import _reject_leakage


@dataclass(frozen=True)
class GraphPeerConfig:
    method_id: str
    version: str
    seed: int
    boundary: tuple[str, ...]
    num_hash_tables: int
    min_jaccard: float
    top_k: int | None
    objective: str
    resolution: float
    iterations: int
    max_vertices: int
    max_edges: int
    baseline_version: str
    min_population: int
    min_support: int
    expected_threshold: float

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(self.__dict__, sort_keys=True).encode()
        ).hexdigest()


def make_graph_config(value: dict, resolution: float) -> GraphPeerConfig:
    minhash, leiden, safety, baseline = (
        value["minhash"],
        value["leiden"],
        value["safety"],
        value["peer_baseline"],
    )
    return GraphPeerConfig(
        str(value["method_id"]),
        str(value["version"]),
        int(value["seed"]),
        tuple(value["boundary"]),
        int(minhash["num_hash_tables"]),
        float(minhash["min_jaccard"]),
        (
            int(minhash["top_k_neighbors_per_identity"])
            if minhash.get("top_k_neighbors_per_identity")
            else None
        ),
        str(leiden["objective"]),
        float(resolution),
        int(leiden["iterations"]),
        int(safety["max_graph_vertices"]),
        int(safety["max_graph_edges"]),
        str(baseline["baseline_version"]),
        int(baseline["min_peer_population"]),
        int(baseline["min_support_count"]),
        float(baseline["expected_prevalence_threshold"]),
    )


def build_graph_features(
    context: DataFrame, config: GraphPeerConfig
) -> tuple[DataFrame, DataFrame]:
    _reject_leakage(context)
    needed = {
        "assessment_date",
        "identidade_id",
        "entitlement_id",
        "birthright",
        "data_quality_blocking",
        "status_identidade",
        "data_concessao",
        *config.boundary,
    }
    missing = needed - set(context.columns)
    if missing:
        raise ValueError(f"Access Context missing graph peer fields: {sorted(missing)}")
    valid = context.where(
        (~F.coalesce("data_quality_blocking", F.lit(True)))
        & (F.lower("status_identidade") == "active")
        & (F.col("data_concessao") <= F.col("assessment_date"))
    )
    identities = (
        valid.select("assessment_date", "identidade_id", *config.boundary)
        .dropDuplicates(["assessment_date", "identidade_id"])
        .withColumn(
            "parent_context",
            F.concat_ws(
                "|", *[F.coalesce(F.col(c), F.lit("UNKNOWN")) for c in config.boundary]
            ),
        )
    )
    # Namespace the feature by structural boundary.  A single Spark-native LSH
    # model can then be fitted without generating meaningful cross-boundary
    # comparisons, avoiding one expensive fit/job per boundary.
    non_birthright = (
        valid.where(~F.coalesce("birthright", F.lit(False)))
        .join(
            identities.select("assessment_date", "identidade_id", "parent_context"),
            ["assessment_date", "identidade_id"],
        )
        .select("assessment_date", "identidade_id", "parent_context", "entitlement_id")
        .distinct()
        .withColumn("feature_key", F.concat_ws("|", "parent_context", "entitlement_id"))
    )
    dictionary = (
        non_birthright.select("feature_key")
        .distinct()
        .withColumn(
            "feature_index", F.row_number().over(Window.orderBy("feature_key")) - 1
        )
    )
    indexed = (
        non_birthright.join(dictionary, "feature_key")
        .groupBy("assessment_date", "identidade_id")
        .agg(F.sort_array(F.collect_set("feature_index")).alias("feature_indices"))
    )
    size = (
        dictionary.agg((F.max("feature_index") + 1).alias("size")).first()["size"] or 0
    )
    vec = F.udf(
        lambda xs: Vectors.sparse(int(size), list(map(int, xs)), [1.0] * len(xs)),
        VectorUDT(),
    )
    features = (
        identities.join(indexed, ["assessment_date", "identidade_id"], "left")
        .where(F.size("feature_indices") > 0)
        .withColumn("features", vec("feature_indices"))
    )
    return features, identities


def candidate_edges(features: DataFrame, config: GraphPeerConfig) -> DataFrame:
    """MinHashLSH similarity join only; no Cartesian identity cross join."""
    empty = (
        features.limit(0)
        .select(
            F.lit(None).cast("string").alias("src_identity"),
            F.lit(None).cast("string").alias("dst_identity"),
            F.lit(None).cast("double").alias("weight"),
            F.lit(None).cast("string").alias("parent_context"),
        )
        .where("false")
    )
    if features.limit(1).count() == 0:
        return empty
    model = MinHashLSH(
        inputCol="features",
        outputCol="hashes",
        numHashTables=config.num_hash_tables,
        seed=config.seed,
    ).fit(features)
    pairs = model.approxSimilarityJoin(
        features.alias("a"),
        features.alias("b"),
        1.0 - config.min_jaccard,
        distCol="distance",
    ).select(
        F.col("datasetA.identidade_id").alias("a"),
        F.col("datasetB.identidade_id").alias("b"),
        F.col("datasetA.assessment_date").alias("pair_assessment_date"),
        F.col("datasetA.parent_context").alias("parent_context"),
    )
    exact = F.udf(
        lambda x, y: (
            float(len(set(x).intersection(y)) / len(set(x).union(y)))
            if x and y
            else 0.0
        ),
        DoubleType(),
    )
    indexed = features.select(
        "identidade_id", "assessment_date", F.col("feature_indices").alias("items")
    )
    edges = (
        pairs.where(F.col("a") < F.col("b"))
        .join(
            indexed.alias("x"),
            (F.col("a") == F.col("x.identidade_id"))
            & (F.col("pair_assessment_date") == F.col("x.assessment_date")),
        )
        .join(
            indexed.alias("y"),
            (F.col("b") == F.col("y.identidade_id"))
            & (F.col("pair_assessment_date") == F.col("y.assessment_date")),
        )
        .withColumn("weight", exact("x.items", "y.items"))
        .where(F.col("weight") >= config.min_jaccard)
        .select(
            F.col("a").alias("src_identity"),
            F.col("b").alias("dst_identity"),
            "weight",
            "parent_context",
        )
    )
    edges = edges.groupBy("src_identity", "dst_identity", "parent_context").agg(
        F.max("weight").alias("weight")
    )
    if config.top_k:
        directed = edges.select(
            F.col("src_identity").alias("identity"),
            F.col("dst_identity").alias("neighbor"),
            "weight",
            "parent_context",
        ).unionByName(
            edges.select(
                F.col("dst_identity").alias("identity"),
                F.col("src_identity").alias("neighbor"),
                "weight",
                "parent_context",
            )
        )
        kept = directed.withColumn(
            "rank",
            F.row_number().over(
                Window.partitionBy("identity").orderBy(F.desc("weight"), "neighbor")
            ),
        ).where(F.col("rank") <= config.top_k)
        edges = (
            kept.select(
                F.least("identity", "neighbor").alias("src_identity"),
                F.greatest("identity", "neighbor").alias("dst_identity"),
                "weight",
                "parent_context",
            )
            .groupBy("src_identity", "dst_identity", "parent_context")
            .agg(F.max("weight").alias("weight"))
        )
    return edges


def leiden_assignments(
    edges: DataFrame, identities: DataFrame, config: GraphPeerConfig
) -> tuple[DataFrame, dict]:
    try:
        import igraph as ig
        import leidenalg
    except ImportError as exc:
        raise RuntimeError(
            "LEIDEN_DEPENDENCY_BLOCKER: install python-igraph and leidenalg"
        ) from exc
    vertex_frame = identities.select("identidade_id").distinct()
    vertex_count = vertex_frame.count()
    edge_count = edges.count()
    if vertex_count > config.max_vertices or edge_count > config.max_edges:
        raise RuntimeError("GRAPH_TOO_LARGE_FOR_LOCAL_LEIDEN")
    vertices = [r[0] for r in vertex_frame.orderBy("identidade_id").collect()]
    edge_rows = (
        edges.select("src_identity", "dst_identity", "weight")
        .orderBy("src_identity", "dst_identity")
        .collect()
    )
    graph = ig.Graph()
    graph.add_vertices(vertices)
    graph.add_edges([(r[0], r[1]) for r in edge_rows])
    graph.es["weight"] = [r[2] for r in edge_rows]
    partition_cls = (
        leidenalg.CPMVertexPartition
        if config.objective == "CPM"
        else leidenalg.ModularityVertexPartition
    )
    kwargs = {
        "weights": graph.es["weight"],
        "seed": config.seed,
        "n_iterations": config.iterations,
    }
    if config.objective == "CPM":
        kwargs["resolution_parameter"] = config.resolution
    part = leidenalg.find_partition(graph, partition_cls, **kwargs)
    membership = list(part.membership)
    members = {}
    for name, cid in zip(vertices, membership):
        members.setdefault(cid, []).append(name)
    records = []
    for cid, names in members.items():
        stable = (
            "GPEER_"
            + hashlib.sha256(
                (config.config_hash + "|" + "|".join(sorted(names))).encode()
            ).hexdigest()[:16]
        )
        reliable = len(names) >= config.min_population and graph.degree(names[0]) > 0
        for name in names:
            records.append(
                (
                    name,
                    stable if reliable else None,
                    str(cid),
                    len(names),
                    "NO_RELIABLE_GRAPH_PEER" if not reliable else "ASSIGNED",
                )
            )
    result = (
        identities.sparkSession.createDataFrame(
            records,
            "identidade_id string, graph_peer_id string, community_id string, community_size int, graph_peer_assignment_status string",
        )
        .join(identities.select("assessment_date", "identidade_id"), "identidade_id")
        .withColumn("graph_model_version", F.lit(config.version))
    )
    components = len(graph.components())
    isolated = sum(1 for d in graph.degree() if d == 0)
    return result, {
        "graph_vertices": len(vertices),
        "final_edges": len(edge_rows),
        "connected_components": components,
        "isolated_vertices": isolated,
        "community_count": len(members),
        "quality": float(part.quality()),
    }


def graph_peer_shadow(
    context: DataFrame, assignments: DataFrame, config: GraphPeerConfig
) -> tuple[DataFrame, DataFrame]:
    """Calculate full-grant graph-peer prevalence; birthrights remain observable."""
    population = (
        assignments.where("graph_peer_id is not null")
        .groupBy("assessment_date", "graph_peer_id")
        .agg(F.countDistinct("identidade_id").alias("population_size"))
    )
    support = (
        context.select("assessment_date", "identidade_id", "entitlement_id")
        .distinct()
        .join(
            assignments.where("graph_peer_id is not null").select(
                "assessment_date", "identidade_id", "graph_peer_id"
            ),
            ["assessment_date", "identidade_id"],
        )
        .groupBy("assessment_date", "graph_peer_id", "entitlement_id")
        .agg(F.countDistinct("identidade_id").alias("support_count"))
    )
    baseline = (
        support.join(population, ["assessment_date", "graph_peer_id"])
        .withColumn("prevalence", F.col("support_count") / F.col("population_size"))
        .withColumn(
            "graph_peer_baseline_reliability",
            F.when(
                (F.col("population_size") >= config.min_population)
                & (F.col("support_count") >= config.min_support),
                "RELIABLE",
            ).otherwise("GRAPH_PEER_BASELINE_NOT_RELIABLE"),
        )
        .withColumn("graph_model_version", F.lit(config.version))
        .withColumn("baseline_version", F.lit(config.baseline_version))
    )
    grants = context.select(
        "grant_id", "assessment_date", "identidade_id", "entitlement_id"
    ).dropDuplicates(["grant_id", "assessment_date"])
    shadow = (
        grants.join(
            assignments.select(
                "assessment_date",
                "identidade_id",
                "graph_peer_id",
                "graph_peer_assignment_status",
            ),
            ["assessment_date", "identidade_id"],
            "left",
        )
        .join(
            baseline.select(
                "assessment_date",
                "graph_peer_id",
                "entitlement_id",
                "population_size",
                "support_count",
                "prevalence",
                "graph_peer_baseline_reliability",
            ),
            ["assessment_date", "graph_peer_id", "entitlement_id"],
            "left",
        )
        .withColumn(
            "graph_peer_expected_status",
            F.when(F.col("graph_peer_id").isNull(), "NO_RELIABLE_GRAPH_PEER")
            .when(
                F.coalesce(F.col("graph_peer_baseline_reliability"), F.lit("MISSING"))
                != "RELIABLE",
                "GRAPH_PEER_INSUFFICIENT",
            )
            .when(
                F.col("prevalence") >= config.expected_threshold, "GRAPH_PEER_EXPECTED"
            )
            .otherwise("GRAPH_PEER_UNEXPECTED"),
        )
        .withColumn("graph_model_version", F.lit(config.version))
        .withColumn("baseline_version", F.lit(config.baseline_version))
    )
    return baseline, shadow
