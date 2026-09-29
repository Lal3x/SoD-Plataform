"""Contracts for the shadow-only peer discovery stage."""

from dataclasses import replace
from datetime import date

import pytest
from pyspark.sql import functions as F

from sod_platform.access_intelligence.experimental.peer_discovery.engine import (
    PeerDiscoveryConfig,
    build_sparse_features,
    run_peer_discovery,
)


def _config():
    return PeerDiscoveryConfig(
        "PDISC001",
        "1.0.0",
        42,
        (2,),
        3,
        "online",
        0.4,
        0.01,
        1.0,
        0.1,
        0.1,
        2,
        "PEERBASE001-1.0.0",
        2,
        1,
        0.5,
    )


def _context(spark):
    rows = []
    for identity, entitlements in [
        ("u1", ["e1", "e2"]),
        ("u2", ["e1", "e2"]),
        ("u3", ["e1", "e3"]),
        ("u4", ["e1", "e3"]),
        ("u5", ["e2", "e3"]),
        ("u6", ["e2", "e3"]),
    ]:
        for entitlement in entitlements:
            rows.append(
                (
                    f"g-{identity}-{entitlement}",
                    date(2025, 2, 1),
                    identity,
                    entitlement,
                    False,
                    "active",
                    date(2025, 1, 1),
                    "C",
                    "S",
                    "Analista",
                    "employee",
                )
            )
    return spark.createDataFrame(
        rows,
        "grant_id string, assessment_date date, identidade_id string, entitlement_id string, data_quality_blocking boolean, status_identidade string, data_concessao date, comunidade string, squad string, cargo string, tipo_identidade string",
    )


def test_sparse_features_are_deterministic_and_deduplicate_entitlements(spark):
    context = _context(spark)
    duplicated = context.unionByName(context.where("grant_id = 'g-u1-e1'"))
    docs, dictionary, _ = build_sparse_features(duplicated, _config())
    assert [
        (r.entitlement_id, r.feature_index)
        for r in dictionary.orderBy("entitlement_id").collect()
    ] == [("e1", 0), ("e2", 1), ("e3", 2)]
    assert (
        docs.where("identidade_id = 'u1'").select("features").first()[0].numNonzeros()
        == 2
    )


def test_sparse_features_exclude_explicit_birthright_when_configured(spark):
    context = _context(spark).withColumn("birthright", F.col("entitlement_id") == "e1")
    excluded_docs, dictionary, _ = build_sparse_features(
        context, replace(_config(), exclude_birthright_features=True)
    )
    assert [
        r.entitlement_id for r in dictionary.orderBy("entitlement_id").collect()
    ] == ["e2", "e3"]
    _docs, dictionary, _ = build_sparse_features(context, _config())
    assert [
        r.entitlement_id for r in dictionary.orderBy("entitlement_id").collect()
    ] == ["e1", "e2", "e3"]
    assert (
        excluded_docs.where("identidade_id = 'u1'")
        .select("features")
        .first()[0]
        .numNonzeros()
        == 1
    )


def test_peer_discovery_rejects_ground_truth_before_fit(spark):
    with pytest.raises(ValueError, match="ground-truth"):
        build_sparse_features(
            _context(spark).withColumn("cenario", F.lit("normal")), _config()
        )


def test_peer_outputs_preserve_identity_and_grant_grain(spark):
    context = _context(spark)
    output = run_peer_discovery(context, _config())
    assignments = output["lda_assignments"]
    assert (
        assignments.groupBy("identidade_id", "assessment_date")
        .count()
        .where("count > 1")
        .count()
        == 0
    )
    shadow = output["peer_expected_shadow"]
    assert (
        shadow.count()
        == context.select("grant_id", "assessment_date").distinct().count()
    )
    baseline = output["peer_baseline"]
    assert (
        baseline.where(
            "support_count > population_size OR population_size <= 0 OR prevalence < 0 OR prevalence > 1"
        ).count()
        == 0
    )
