"""Read-only audit of already frozen graph, LDA and current outputs.

This script does not fit models or modify runtime tables. Ground truth is loaded
only after all unlabelled diagnostics have been computed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pyspark.sql import functions as F

from sod_platform.bronze.ingestion.spark import create_spark_session
from sod_platform.common.env import load_project_env


def distribution(frame, column):
    return {str(row[0]): row[1] for row in frame.groupBy(column).count().collect()}


def quantiles(frame, column):
    values = frame.where(F.col(column).isNotNull()).approxQuantile(
        column, [0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99, 1.0], 0.001
    )
    return dict(
        zip(["p10", "p25", "median", "p75", "p90", "p95", "p99", "max"], values)
    )


def main():
    root = Path.cwd()
    load_project_env(root)
    spark = create_spark_session(root, "offline-graph-peer-audit")
    spark.sparkContext.setLogLevel("ERROR")
    try:
        context = spark.table("sod.silver.access_context")
        current = spark.table("sod.access_intelligence.expected_access")
        fallback = spark.table("sod.access_intelligence.hierarchical_fallback")
        lda = spark.table("sod.access_intelligence.peer_expected_shadow")
        graph = spark.table("sod.access_intelligence.graph_peer_expected_shadow")
        assignments = spark.table("sod.access_intelligence.graph_peer_assignments")
        baseline = spark.table("sod.access_intelligence.graph_peer_baseline")
        edges = spark.table("sod.access_intelligence.graph_peer_edges")
        grain = ["grant_id", "assessment_date"]
        joined = (
            context.select(*grain, "identidade_id", "entitlement_id", "comunidade")
            .join(current.select(*grain, "expected_access_status"), grain)
            .join(fallback.select(*grain, "selected_prevalence"), grain)
            .join(
                lda.select(
                    *grain,
                    F.col("prevalence").alias("lda_prevalence"),
                    "peer_expected_status",
                ),
                grain,
            )
            .join(
                graph.select(
                    *grain,
                    F.col("prevalence").alias("graph_prevalence"),
                    "graph_peer_expected_status",
                    "graph_peer_id",
                ),
                grain,
            )
        ).cache()
        all_count = joined.count()
        insufficient = joined.where("expected_access_status = 'INSUFFICIENT_EVIDENCE'")
        # Selected fallback prevalence is NULL when no level is sufficient.
        # Community prevalence is the comparable descriptive reference used for
        # lift diagnostics; it is not substituted into EA001.
        community = (
            spark.table("sod.access_intelligence.observed_baseline")
            .where("baseline_level = 'COMUNIDADE'")
            .select(
                "assessment_date",
                "comunidade",
                "entitlement_id",
                F.col("prevalence").alias("current_community_prevalence"),
            )
        )
        compared = insufficient.join(
            community, ["assessment_date", "comunidade", "entitlement_id"], "left"
        )
        compared = compared.withColumn(
            "leiden_delta",
            F.col("graph_prevalence") - F.col("current_community_prevalence"),
        ).withColumn(
            "leiden_lift",
            F.when(
                F.col("current_community_prevalence") > 0,
                F.col("graph_prevalence") / F.col("current_community_prevalence"),
            ),
        )
        degrees = (
            edges.select(F.col("src_identity").alias("identity"))
            .unionByName(edges.select(F.col("dst_identity").alias("identity")))
            .groupBy("identity")
            .count()
            .withColumnRenamed("count", "degree")
        )
        sizes = assignments.groupBy("community_id").agg(
            F.first("community_size").cast("double").alias("community_size")
        )
        edge_rows = (
            edges.orderBy("src_identity", "dst_identity")
            .select("src_identity", "dst_identity", "weight", "parent_context")
            .toLocalIterator()
        )
        digest = hashlib.sha256()
        for row in edge_rows:
            digest.update(f"{row[0]}|{row[1]}|{row[2]:.12f}|{row[3]}\n".encode())
        graph_hash = digest.hexdigest()
        unlabelled = {
            "graph_sha256": graph_hash,
            "grant_cardinality": {
                "context": context.count(),
                "joined": all_count,
                "graph_shadow": graph.count(),
                "graph_duplicates": graph.groupBy(*grain)
                .count()
                .where("count > 1")
                .count(),
            },
            "edge_integrity": {
                "edges": edges.count(),
                "self_edges": edges.where("src_identity = dst_identity").count(),
                "duplicate_pairs": edges.groupBy("src_identity", "dst_identity")
                .count()
                .where("count > 1")
                .count(),
                "cross_boundary_edges": edges.join(
                    assignments.select(
                        F.col("identidade_id").alias("src_identity"), "assessment_date"
                    )
                    .join(
                        context.select(
                            "identidade_id", "comunidade", "tipo_identidade"
                        ).dropDuplicates(["identidade_id"]),
                        F.col("src_identity") == F.col("identidade_id"),
                    )
                    .select(
                        "src_identity",
                        F.concat_ws("|", "comunidade", "tipo_identidade").alias(
                            "expected_parent_context"
                        ),
                    ),
                    "src_identity",
                )
                .where("parent_context != expected_parent_context")
                .count(),
            },
            "degree": quantiles(degrees, "degree"),
            "community_size": quantiles(sizes, "community_size"),
            "microcommunities_under_10": sizes.where("community_size < 10").count(),
            "usable_peer_count": assignments.where("graph_peer_id is not null")
            .select("graph_peer_id")
            .distinct()
            .count(),
            "assignment_status": distribution(
                assignments, "graph_peer_assignment_status"
            ),
            "graph_status": distribution(graph, "graph_peer_expected_status"),
            "lda_status": distribution(lda, "peer_expected_status"),
            "current_status": distribution(current, "expected_access_status"),
            "baseline_invalid": baseline.where(
                "support_count > population_size OR population_size <= 0 OR prevalence < 0 OR prevalence > 1"
            ).count(),
            "insufficient_grants": insufficient.count(),
            "insufficient_graph_status": distribution(
                insufficient, "graph_peer_expected_status"
            ),
            "insufficient_lda_status": distribution(
                insufficient, "peer_expected_status"
            ),
            "comparison_reference": "COMUNIDADE observed prevalence; EA001 selected_prevalence remains NULL when insufficient",
            "reference_coverage": compared.where(
                "current_community_prevalence is not null"
            ).count(),
            "graph_prevalence_coverage_in_current_insufficient": compared.where(
                "graph_prevalence is not null"
            ).count(),
            "delta": quantiles(compared, "leiden_delta"),
            "lift": quantiles(compared, "leiden_lift"),
            "gain_ge_010": compared.where("leiden_delta >= 0.10").count(),
            "gain_ge_020": compared.where("leiden_delta >= 0.20").count(),
            "graph_reliable_coverage": graph.where(
                "graph_peer_baseline_reliability = 'RELIABLE'"
            ).count(),
        }
        print("UNLABELLED_AUDIT=" + json.dumps(unlabelled, sort_keys=True), flush=True)
        print("FROZEN_OUTPUTS_CONFIRMED_BEFORE_LABEL_READ", flush=True)
        labels = spark.read.option("header", True).csv(
            str(root / "tests/fixtures/gabarito.csv")
        )
        evaluated = joined.join(labels, ["identidade_id", "entitlement_id"])
        normal = evaluated.where(
            "cenario = 'normal' AND expected_access_status = 'INSUFFICIENT_EVIDENCE'"
        )
        indevido = evaluated.where("classificacao_esperada = 'INDEVIDO'")
        offline = {
            "labelled": evaluated.count(),
            "normal_currently_insufficient": normal.count(),
            "normal_graph_status": distribution(normal, "graph_peer_expected_status"),
            "normal_lda_status": distribution(normal, "peer_expected_status"),
            "critical_total": indevido.count(),
            "critical_false_positive_grants": [
                r[0]
                for r in indevido.where(
                    "graph_peer_expected_status = 'GRAPH_PEER_EXPECTED'"
                )
                .select("grant_id")
                .orderBy("grant_id")
                .collect()
            ],
            "contaminated_communities": [
                r.asDict()
                for r in evaluated.where("graph_peer_id is not null")
                .groupBy("graph_peer_id")
                .agg(
                    F.countDistinct("identidade_id").alias("population"),
                    F.sum(
                        F.when(
                            F.col("classificacao_esperada") == "PADRAO", 1
                        ).otherwise(0)
                    ).alias("PADRAO"),
                    F.sum(
                        F.when(
                            F.col("classificacao_esperada") == "LEGITIMO", 1
                        ).otherwise(0)
                    ).alias("LEGITIMO"),
                    F.sum(
                        F.when(
                            F.col("classificacao_esperada") == "INDEVIDO", 1
                        ).otherwise(0)
                    ).alias("INDEVIDO"),
                )
                .where("INDEVIDO > 0")
                .orderBy("graph_peer_id")
                .collect()
            ],
        }
        output = root / "docs" / "leiden-peer-discovery-offline-audit-2026-09-27.json"
        output.write_text(
            json.dumps(
                {"unlabelled": unlabelled, "offline": offline}, indent=2, sort_keys=True
            )
            + "\n",
            encoding="utf-8",
        )
        print(
            "OFFLINE_AUDIT_SUMMARY="
            + json.dumps(
                {k: v for k, v in offline.items() if k != "contaminated_communities"},
                sort_keys=True,
            ),
            flush=True,
        )
        print("AUDIT_ARTIFACT=" + str(output), flush=True)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
