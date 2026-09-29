"""PDISC002 contracts: sparse global features, abstention and shadow grain."""
from datetime import date

import pytest
from pyspark.sql import functions as F

from sod_platform.access_intelligence.experimental.peer_discovery.nmf_hdbscan import (
    NmfHdbscanConfig,
    build_nmf_features,
    run_nmf_hdbscan,
)


def _config(**overrides):
    values = {
        "method_id": "PDISC002", "version": "1.0.0", "seed": 42,
        "components": (2,), "max_iter": 100, "l2_normalize": True,
        "max_sparse_bytes": 1_000_000, "min_cluster_size": 2,
        "min_samples": 1, "metric": "euclidean", "cluster_selection_method": "eom",
        "cluster_selection_epsilon": 0.0, "min_peer_population": 2,
        "min_support": 1, "expected_threshold": 0.8,
    }
    values.update(overrides)
    return NmfHdbscanConfig(**values)


def _context(spark):
    rows = []
    for identity, entitlements in (("u1", ("birth", "a", "b")), ("u2", ("birth", "a", "b")),
                                   ("u3", ("birth", "c", "d")), ("u4", ("birth", "c", "d")),
                                   ("u5", ("birth",))):
        for entitlement in entitlements:
            rows.append((f"g-{identity}-{entitlement}", date(2025, 2, 1), identity, entitlement,
                         entitlement == "birth", False, "active", date(2025, 1, 1)))
    return spark.createDataFrame(rows, "grant_id string, assessment_date date, identidade_id string, entitlement_id string, birthright boolean, data_quality_blocking boolean, status_identidade string, data_concessao date")


def test_nmf_features_exclude_only_birthrights_and_reject_labels(spark):
    context = _context(spark)
    indexed, dictionary, identities = build_nmf_features(context)
    assert [r.entitlement_id for r in dictionary.orderBy("entitlement_id").collect()] == ["a", "b", "c", "d"]
    assert identities.count() == 5
    assert indexed.where("entitlement_id = 'birth'").count() == 0
    with pytest.raises(ValueError, match="ground-truth"):
        build_nmf_features(context.withColumn("cenario", F.lit("normal")))


def test_global_nmf_hdbscan_preserves_abstention_and_grant_grain(spark):
    context = _context(spark)
    result = run_nmf_hdbscan(context, _config())
    assignments = result["assignments"]
    assert assignments.count() == 5
    assert assignments.where("identidade_id = 'u5' AND peer_status = 'NO_MODEL_FEATURES'").count() == 1
    assert result["shadow"].count() == context.select("grant_id", "assessment_date").distinct().count()
    assert result["baseline"].where("support_count > population_size OR population_size <= 0 OR prevalence < 0 OR prevalence > 1").count() == 0
    assert result["metrics"]["model_frozen"] == "NMF_HDBSCAN MODEL FROZEN FOR OFFLINE EVALUATION"


def test_memory_gate_blocks_before_driver_sparse_collection(spark):
    with pytest.raises(RuntimeError, match="GLOBAL_MODEL_MEMORY_SAFETY_BLOCK"):
        run_nmf_hdbscan(_context(spark), _config(max_sparse_bytes=1))
