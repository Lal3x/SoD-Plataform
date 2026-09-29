"""Standalone materializer for PDISC002; it never invokes official stages."""
from __future__ import annotations

from pathlib import Path

from pyspark.sql import SparkSession

from sod_platform.access_intelligence.pipeline import _source_run_id, _write_snapshot

from .nmf_hdbscan import load_nmf_hdbscan_config, run_nmf_hdbscan

OUTPUTS = {
    "feature_dictionary": "sod.access_intelligence.peer_nmf_feature_dictionary",
    "components": "sod.access_intelligence.peer_nmf_components",
    "identity_vectors": "sod.access_intelligence.peer_nmf_identity_vectors",
    "assignments": "sod.access_intelligence.peer_hdbscan_assignments",
    "baseline": "sod.access_intelligence.peer_nmf_hdbscan_baseline",
    "shadow": "sod.access_intelligence.peer_nmf_hdbscan_expected_shadow",
}


def run_nmf_hdbscan_shadow(spark: SparkSession, config_path: Path) -> dict:
    """Run PDISC002 against Access Context only and materialize separate tables."""
    context = spark.table("sod.silver.access_context")
    config = load_nmf_hdbscan_config(config_path)
    result = run_nmf_hdbscan(context, config)
    for key, table in OUTPUTS.items():
        _write_snapshot(result[key], table)
    return {"run_id": _source_run_id(context), "method_id": config.method_id,
            "model_version": config.version, "config_hash": config.config_hash,
            **result["metrics"]}
