"""Safety and mathematical contracts for the independent graph shadow stage."""

from datetime import date

import pytest
from pyspark.sql import functions as F

from sod_platform.access_intelligence.experimental.peer_discovery.graph_engine import (
    GraphPeerConfig,
    build_graph_features,
    candidate_edges,
    graph_peer_shadow,
    leiden_assignments,
)


def _config(**overrides):
    values = {
        "method_id": "GPDISC001",
        "version": "1.0.0",
        "seed": 42,
        "boundary": ("comunidade", "tipo_identidade"),
        "num_hash_tables": 12,
        "min_jaccard": 0.5,
        "top_k": 3,
        "objective": "CPM",
        "resolution": 0.5,
        "iterations": -1,
        "max_vertices": 100,
        "max_edges": 100,
        "baseline_version": "GRAPHPEERBASE001-1.0.0",
        "min_population": 2,
        "min_support": 2,
        "expected_threshold": 0.8,
    }
    values.update(overrides)
    return GraphPeerConfig(**values)


def _context(spark):
    rows = []
    for identity, community, items in (
        ("u1", "A", ("common", "x", "y")),
        ("u2", "A", ("common", "x", "y")),
        ("u3", "A", ("common", "x")),
        ("u4", "B", ("common", "x", "y")),
        ("u5", "A", ("common",)),
    ):
        for item in items:
            rows.append(
                (
                    f"{identity}-{item}",
                    date(2025, 1, 31),
                    identity,
                    item,
                    item == "common",
                    False,
                    "active",
                    date(2025, 1, 1),
                    community,
                    "employee",
                )
            )
    return spark.createDataFrame(
        rows,
        "grant_id string, assessment_date date, identidade_id string, entitlement_id string, birthright boolean, data_quality_blocking boolean, status_identidade string, data_concessao date, comunidade string, tipo_identidade string",
    )


def test_graph_features_reject_labels_and_keep_birthright_in_grants(spark):
    context = _context(spark)
    with pytest.raises(ValueError, match="ground-truth"):
        build_graph_features(context.withColumn("cenario", F.lit("normal")), _config())
    features, identities = build_graph_features(context, _config())
    assert features.count() == 4  # u5 has birthright only and abstains
    assert identities.count() == 5
    assert features.where("identidade_id = 'u1'").first().features.numNonzeros() == 2
    assert context.where("entitlement_id = 'common'").count() == 5


def test_sparse_edges_leiden_and_peer_baseline_contract(spark):
    context = _context(spark)
    config = _config()
    features, identities = build_graph_features(context, config)
    edges = candidate_edges(features.cache(), config).cache()
    assert edges.where("src_identity = dst_identity").count() == 0
    assert (
        edges.groupBy("src_identity", "dst_identity").count().where("count > 1").count()
        == 0
    )
    assert (
        edges.where("src_identity = 'u1' AND dst_identity = 'u2'").first().weight == 1.0
    )
    assert edges.where("src_identity = 'u1' AND dst_identity = 'u4'").count() == 0
    assignments, _ = leiden_assignments(edges, identities, config)
    assert assignments.count() == identities.count()
    assert (
        assignments.where(
            "identidade_id = 'u5' AND graph_peer_assignment_status = 'NO_RELIABLE_GRAPH_PEER'"
        ).count()
        == 1
    )
    baseline, shadow = graph_peer_shadow(context, assignments, config)
    assert (
        baseline.where(
            "support_count > population_size OR prevalence < 0 OR prevalence > 1"
        ).count()
        == 0
    )
    assert shadow.count() == context.count()
    assert shadow.where("entitlement_id = 'common'").count() == 5  # birthright retained


def test_driver_safety_gate_precedes_collection(spark):
    features, identities = build_graph_features(_context(spark), _config())
    edges = candidate_edges(features.cache(), _config())
    with pytest.raises(RuntimeError, match="GRAPH_TOO_LARGE_FOR_LOCAL_LEIDEN"):
        leiden_assignments(edges, identities, _config(max_vertices=1))
