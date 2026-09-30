"""Frozen V2 table contracts used by the read-only dashboard."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOLD_TABLE = "sod.gold.sod_assessment_gold001"
EVIDENCE_TABLE = "sod.evidence.evidence_facts_ev001_1_3_1"
VALIDATION_TABLES = {
    "summary": "sod.validation.executive_metrics",
    "classes": "sod.validation.class_metrics",
    "confusion": "sod.validation.confusion_matrix",
    "scenarios": "sod.validation.scenario_metrics",
    "evaluation": "sod.validation.policy_evaluation",
}
DATASET_VERSION = "V2"
