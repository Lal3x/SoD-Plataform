"""Offline LDA peer shadow materialization, separate from the V2 runtime."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from pyspark.sql import SparkSession

from sod_platform.access_intelligence.pipeline import _source_run_id, _write_snapshot
from sod_platform.observability.access_intelligence import (
    append_component_run,
    distribution,
)

from .engine import load_peer_discovery_config, run_peer_discovery

OUTPUTS = {
    "feature_dictionary": "sod.access_intelligence.peer_feature_dictionary",
    "lda_assignments": "sod.access_intelligence.peer_lda_assignments",
    "role_profiles": "sod.access_intelligence.peer_role_profiles",
    "frequent_patterns": "sod.access_intelligence.peer_frequent_patterns",
    "association_rules": "sod.access_intelligence.peer_association_rules",
    "peer_baseline": "sod.access_intelligence.peer_baseline",
    "peer_expected_shadow": "sod.access_intelligence.peer_expected_shadow",
}


def run_lda_shadow(spark: SparkSession, config_path: Path) -> dict:
    """Run the historical peer shadow without invoking official stages."""
    context = spark.table("sod.silver.access_context")
    run_id = _source_run_id(context)
    peer_config = load_peer_discovery_config(config_path)
    if not peer_config:
        return {"run_id": run_id, "peer_discovery_shadow": "DISABLED"}
    started_at, monotonic_started = datetime.now(UTC), time.monotonic()
    try:
        peer = run_peer_discovery(context, peer_config)
        for key, table in OUTPUTS.items():
            _write_snapshot(peer[key], table)
        assignments = peer["lda_assignments"]
        shadow = peer["peer_expected_shadow"]
        current_expected = spark.table("sod.access_intelligence.expected_access")
        comparison = current_expected.select(
            "grant_id", "assessment_date", "expected_access_status"
        ).join(
            shadow.select("grant_id", "assessment_date", "peer_expected_status"),
            ["grant_id", "assessment_date"],
            "inner",
        )
        metrics = {
            "input_identity_count": assignments.select("identidade_id").distinct().count(),
            "input_grant_count": context.select("grant_id").distinct().count(),
            "vocabulary_size": peer["feature_dictionary"].count(),
            "lda_topics": peer["model_selection"]["selected_k"],
            "peer_groups": assignments.select("peer_group_id").distinct().count(),
            "high_confidence_peers": assignments.where("peer_confidence = 'HIGH_CONFIDENCE'").count(),
            "ambiguous_peers": assignments.where("peer_confidence = 'AMBIGUOUS'").count(),
            "low_confidence_peers": assignments.where("peer_confidence = 'LOW_CONFIDENCE'").count(),
            "peer_baseline_rows": peer["peer_baseline"].count(),
            "patterns_count": peer["frequent_patterns"].count(),
            "shadow_status": distribution(shadow, "peer_expected_status"),
            "current_vs_peer": {
                f"{row['expected_access_status']}→{row['peer_expected_status']}": row["count"]
                for row in comparison.groupBy(
                    "expected_access_status", "peer_expected_status"
                ).count().collect()
            },
            "current_insufficient_with_reliable_peer": comparison.where(
                "expected_access_status = 'INSUFFICIENT_EVIDENCE' "
                "AND peer_expected_status = 'PEER_EXPECTED'"
            ).count(),
            "model_selection": peer["model_selection"],
        }
        append_component_run(
            spark, run_id=run_id, component="peer_discovery_shadow", status="success",
            started_at=started_at,
            duration_seconds=round(time.monotonic() - monotonic_started, 3),
            metrics=metrics,
        )
        return {"run_id": run_id, "peer_discovery_shadow": metrics}
    except Exception:
        append_component_run(
            spark, run_id=run_id, component="peer_discovery_shadow", status="failed",
            started_at=started_at,
            duration_seconds=round(time.monotonic() - monotonic_started, 3),
            metrics={"error": "peer_discovery_failed"},
        )
        raise
