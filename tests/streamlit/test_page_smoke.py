"""Render every page against small repository doubles."""

from pathlib import Path
from typing import ClassVar

import pytest
from streamlit.testing.v1 import AppTest

from apps.streamlit.data import factory

PAGES = Path(__file__).resolve().parents[2] / "apps/streamlit/pages"


class FakeFrame:
    columns: ClassVar[list[str]] = [
        "identity_community",
        "squad",
        "cargo",
        "identity_type",
        "sigla_id",
        "entitlement_id",
        "policy_decision",
        "risk_band",
        "expected_access_state",
        "privileged",
        "regulatory_scope",
        "sigla_publica",
        "birthright",
        "approval_evidence_status",
        "certification_status",
        "policy_rule_id",
        "criticidade",
    ]


class FakeGold:
    def frame(self):
        return FakeFrame()

    def get_filter_options(self, fields):
        return {field: [] for field in fields}

    def get_executive_metrics(self):
        return {
            "total": 1,
            "review": 0,
            "remediation": 0,
            "privileged": 0,
            "regulatory": 0,
        }

    def distribution(self, field, filters=None):
        return [{field: "PADRAO" if field == "policy_decision" else "LOW", "count": 1}]

    def get_policy_distribution(self):
        return [{"policy_decision": "PADRAO", "count": 1}]

    def get_risk_distribution(self):
        return [{"risk_band": "LOW", "count": 1}]

    def get_policy_risk_matrix(self):
        return [{"policy_decision": "PADRAO", "risk_band": "LOW", "count": 1}]

    def get_community_analysis(self, sort_by="total_grants"):
        return [
            {
                "identity_community": "C",
                "total_grants": 1,
                "indevido": 0,
                "indevido_rate": 0.0,
                "revisao": 0,
                "review_rate": 0.0,
            }
        ]

    def get_application_analysis(self):
        return [{"sigla_id": "S", "total_grants": 1}]

    def get_entitlement_analysis(self):
        return [{"entitlement_id": "E", "total_grants": 1}]

    def get_expected_access_analysis(self):
        return [{"expected_access_state": "EXPECTED", "count": 1}]

    def get_prevalence_distribution(self):
        return [{"prevalence_band": 0.9, "count": 1}]

    def get_baseline_analysis(self):
        return [{"selected_baseline_level": "COMUNIDADE", "grants": 1}]

    def get_review_analysis(self, field, limit=30):
        return [{field: "C", "total_grants": 1, "review_grants": 0, "review_rate": 0.0}]

    def search_assessments(self, *args, **kwargs):
        return []

    def count_assessments(self, *args, **kwargs):
        return 0

    def get_review_queue(self, *args, **kwargs):
        return []

    def get_remediation_queue(self, *args, **kwargs):
        return []


class FakeValidation:
    def get_validation_summary(self):
        return {
            "runtime_grants": 1,
            "labeled_grants": 1,
            "unlabeled_grants": 0,
            "overall_exact_accuracy": 1.0,
            "automated_decision_accuracy": 1.0,
            "automation_rate": 1.0,
            "review_rate": 0.0,
            "critical_false_safe_count": 0,
            "false_indevido_count": 0,
            "normal_identifiability_90": 1.0,
            "indevido_critical_risk_rate": 1.0,
        }

    def get_class_metrics(self):
        return [{"class_name": "PADRAO", "precision": 1.0, "recall": 1.0, "f1": 1.0}]

    def get_confusion_matrix(self):
        return [{"ground_truth": "PADRAO", "predicted_policy": "PADRAO", "count": 1}]

    def get_scenario_metrics(self):
        return [{"scenario": "normal", "total": 1, "accuracy": 1.0}]


class FakeObservability:
    def get_pipeline_counts(self):
        return [{"stage": "Gold", "count": 1}]

    def get_data_quality_metrics(self):
        return []

    def get_quarantine_metrics(self):
        return []

    def get_reconciliation_metrics(self):
        return {"policy_mismatch": 0}

    def get_versions(self):
        return [{"dataset_version": "V2"}]

    def get_lineage(self):
        return {"output_table": "sod.gold.sod_assessment_gold001"}

    def get_processing_timestamp(self):
        return None


@pytest.mark.parametrize(
    "page",
    [
        "executive_overview",
        "access_business",
        "risk_prioritization",
        "explainability",
        "data_analysis",
        "poc_validation",
        "observability",
    ],
)
def test_page_renders(monkeypatch, page):
    monkeypatch.setattr(factory, "gold", lambda: FakeGold())
    monkeypatch.setattr(factory, "validation", lambda: FakeValidation())
    monkeypatch.setattr(factory, "observability", lambda: FakeObservability())
    app = AppTest.from_file(str(PAGES / f"{page}.py"), default_timeout=15).run()
    assert not app.exception
    assert not app.error
    assert app.title
