"""Persisted metadata and quality observations; missing sources stay unavailable."""

from __future__ import annotations

import json

from pyspark.sql import functions as F

from apps.streamlit.config import GOLD_TABLE, ROOT
from apps.streamlit.data.base import SparkSource


class ObservabilityRepository:
    def __init__(self, source: SparkSource):
        self.source = source

    def _optional(self, table: str):
        return self.source.table(table) if self.source.spark.catalog.tableExists(table) else None

    def get_pipeline_counts(self):
        tables = {"Bronze grants": "sod.bronze.access_assignments",
                  "Silver grants": "sod.silver.iga_access_assignments",
                  "Access Context": "sod.silver.access_context",
                  "Expected Access": "sod.access_intelligence.expected_access",
                  "Evidence summaries": "sod.evidence.evidence_summary_ev001_1_3_1",
                  "Evidence facts": "sod.evidence.evidence_facts_ev001_1_3_1",
                  "Policy": "sod.policy.policy_decisions_pd002_1_0_1",
                  "Risk": "sod.risk.risk_assessment_risk001_1_0_0",
                  "Gold": GOLD_TABLE}
        return [{"stage": label, "table": name, "count": frame.count() if frame is not None else None}
                for label, name in tables.items() if (frame := self._optional(name)) is not None]

    def get_data_quality_metrics(self):
        frame = self._optional("sod.quality.data_quality_results")
        if frame is None:
            return []
        dimension = next((c for c in ("status", "severity", "rule_id") if c in frame.columns), None)
        return (self.source.records(frame.groupBy(dimension).count(), 100) if dimension
                else [{"count": frame.count()}])

    def get_quarantine_metrics(self):
        frame = self._optional("sod.quality.quarantine")
        if frame is None:
            return []
        dimension = next((c for c in ("reason", "dq_rule", "source_name") if c in frame.columns), None)
        return (self.source.records(frame.groupBy(dimension).count(), 100) if dimension
                else [{"count": frame.count()}])

    def get_reconciliation_metrics(self):
        return self.get_runtime_metadata().get("reconciliation", {})

    def get_runtime_metadata(self):
        path = ROOT / "artifacts/freezes/v2-gold-runtime-freeze.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def get_versions(self):
        frame = self.source.table(GOLD_TABLE)
        fields = [c for c in ("dataset_version", "gold_version", "evidence_version",
                              "policy_version", "risk_version", "expected_access_version",
                              "baseline_version") if c in frame.columns]
        return self.source.records(frame.select(*fields).distinct(), 10)

    def get_snapshots(self):
        metadata = self.get_runtime_metadata()
        return {"output_snapshot": metadata.get("output_snapshot"),
                "input_snapshots": metadata.get("input_snapshots", {})}

    def get_lineage(self):
        metadata = self.get_runtime_metadata()
        return {"input_tables": metadata.get("input_tables", {}),
                "input_snapshots": metadata.get("input_snapshots", {}),
                "output_table": metadata.get("output_table"),
                "output_snapshot": metadata.get("output_snapshot")}

    def get_processing_timestamp(self):
        frame = self.source.table(GOLD_TABLE, {"processing_timestamp"})
        return frame.agg(F.max("processing_timestamp")).first()[0]
