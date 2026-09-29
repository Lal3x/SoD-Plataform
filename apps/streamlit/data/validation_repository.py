"""Offline V2 validation mart, isolated from operational repositories."""

from pyspark.sql import functions as F

from apps.streamlit.config import VALIDATION_TABLES
from apps.streamlit.data.base import SparkSource


class ValidationRepository:
    def __init__(self, source: SparkSource):
        self.source = source

    def _rows(self, key: str, required: set[str], limit: int = 200):
        return self.source.records(self.source.table(VALIDATION_TABLES[key], required), limit)

    def get_validation_summary(self):
        return self._rows("summary", {"runtime_grants", "labeled_grants", "unlabeled_grants",
                                      "overall_exact_accuracy", "automation_rate", "review_rate"}, 1)[0]

    def get_class_metrics(self):
        return self._rows("classes", {"class_name", "precision", "recall", "f1", "support"})

    def get_confusion_matrix(self):
        return self._rows("confusion", {"ground_truth", "predicted_policy", "count"})

    def get_scenario_metrics(self):
        return self._rows("scenarios", {"scenario", "total", "accuracy", "review_rate"})

    def get_automation_metrics(self):
        summary = self.get_validation_summary()
        return {key: summary[key] for key in ("automation_rate", "review_rate", "automated_decision_accuracy")}

    def get_safety_metrics(self):
        summary = self.get_validation_summary()
        return {key: summary[key] for key in ("critical_false_safe_count", "false_indevido_count")}

    def get_normal_observability_metrics(self):
        return {"normal_identifiability_90": self.get_validation_summary()["normal_identifiability_90"]}

    def get_risk_validation(self):
        return {"indevido_critical_risk_rate": self.get_validation_summary()["indevido_critical_risk_rate"]}

    def get_labeled_distribution(self):
        frame = self.source.table(VALIDATION_TABLES["evaluation"], {"ground_truth_class"})
        return self.source.records(frame.groupBy("ground_truth_class").agg(F.count("*").alias("count")), 10)
