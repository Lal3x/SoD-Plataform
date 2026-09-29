"""Versioned input and output contracts for the Evidence Engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

METHOD_ID = "EV001"
VERSION = "1.3.1"

CATEGORIES = frozenset(
    {
        "EXPLICIT_CONTEXT",
        "AUTHORIZATION",
        "ANALYTICAL_EXPECTATION",
        "TEMPORAL_USAGE",
        "DATA_QUALITY",
        "SENSITIVITY",
    }
)
RELIABILITY_LEVELS = frozenset({"HIGH", "MEDIUM", "LOW", "UNKNOWN"})

ACCESS_CONTEXT_REQUIRED = frozenset(
    {
        "grant_id",
        "assessment_date",
        "_silver_run_id",
        "identidade_id",
        "tipo_identidade",
        "comunidade",
        "squad",
        "cargo",
        "entitlement_id",
        "sigla_id",
        "comunidade_dona_sigla",
        "birthright",
        "sigla_publica",
        "cross_community",
        "approval_relevance",
        "data_aprovacao",
        "certification_decisao",
        "certification_data_revisao",
        "certification_campaign_id",
        "certification_pending_count",
        "data_concessao",
        "ultimo_uso",
        "inherited_access_candidate",
        "identity_history_complete",
        "no_usage_recorded",
        "usage_coverage",
        "access_age_days",
        "days_since_last_use",
        "entitlement_privileged",
        "application_criticality",
        "classificacao_dado",
        "regulatory_scope",
        "data_quality_blocking",
        "source_snapshot_id",
    }
)

ACCESS_CONTEXT_OPTIONAL = {
    "approval_linkage_quality": "string",
    "approval_to_grant_delta_days": "integer",
    "request_id": "string",
}

EXPECTED_ACCESS_REQUIRED = frozenset(
    {
        "grant_id",
        "assessment_date",
        "expected_access_status",
        "expected_access_reason",
        "explicit_anchor_flag",
        "explicit_anchor_reason",
        "selected_baseline_level",
        "fallback_depth",
        "population_size",
        "support_count",
        "prevalence",
        "expectation_evidence_strength",
        "expected_access_method_id",
        "expected_access_method_version",
        "hard_trusted_rule_version",
        "baseline_version",
        "fallback_version",
        "source_snapshot_id",
        "baseline_source_snapshot_id",
        "baseline_timestamp",
        "evaluated_at",
    }
)


@dataclass(frozen=True)
class EvidenceEngineConfig:
    """Supported upstream versions and the evidence bundle version."""

    method_id: str
    version: str
    supported_expected_access_method_id: str
    supported_expected_access_method_version: str
    supported_hard_trusted_rule_version: str
    supported_baseline_version: str
    supported_fallback_version: str

    def __post_init__(self) -> None:
        if not all(vars(self).values()):
            raise ValueError("Evidence Engine identifiers and versions must be non-empty")
        if self.method_id != METHOD_ID:
            raise ValueError(f"Unsupported Evidence Engine method_id: {self.method_id}")


def load_evidence_engine_config(path: Path) -> EvidenceEngineConfig:
    """Load the explicit EV001 compatibility contract."""
    try:
        values = yaml.safe_load(path.read_text(encoding="utf-8"))["evidence_engine"]
        return EvidenceEngineConfig(**{field: str(values[field]) for field in EvidenceEngineConfig.__dataclass_fields__})
    except (KeyError, OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        raise ValueError(f"Invalid Evidence Engine configuration {path}: {exc}") from exc
