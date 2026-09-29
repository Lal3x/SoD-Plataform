"""Strict configuration contract for PD001/1.0.0."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

POLICY_ID = "PD001"
POLICY_VERSION = "1.0.0"
RULE_IDS = frozenset(
    {
        "R001",
        "R010",
        "R015",
        "R020",
        "R030",
        "R040",
        "R041",
        "R060",
        "R065",
        "R066",
        "R070",
        "R080",
        "R090",
        "R100",
        "R110",
    }
)
TERMINAL_RULES = frozenset({"R001", "R010", "R015", "R020", "R030", "R040", "R110"})
CLASSIFICATIONS = frozenset(
    {"PADRAO", "LEGITIMO", "REVISAO", "REVISAO_DADOS", "POTENCIALMENTE_INDEVIDO"}
)


@dataclass(frozen=True)
class RuleConfig:
    rule_id: str
    rule_version: str
    rule_type: str
    priority: int
    policy_source: str
    reason_code: str
    enabled: bool
    classification: str | None = None


@dataclass(frozen=True)
class PolicyDecisionConfig:
    policy_id: str
    version: str
    supported_evidence_method_id: str
    supported_evidence_version: str
    rules: tuple[RuleConfig, ...]

    def __post_init__(self) -> None:
        if (self.policy_id, self.version) != (POLICY_ID, POLICY_VERSION):
            raise ValueError("Unsupported Policy Decision version")
        ids = [rule.rule_id for rule in self.rules]
        if set(ids) != RULE_IDS or len(ids) != len(set(ids)):
            raise ValueError(
                "PD001 rule catalog must contain each approved rule exactly once"
            )
        if len({rule.priority for rule in self.rules}) != len(self.rules):
            raise ValueError("PD001 rule priorities must be unique")
        for rule in self.rules:
            if rule.rule_id in TERMINAL_RULES:
                if (
                    rule.rule_type != "TERMINAL"
                    or rule.classification not in CLASSIFICATIONS
                ):
                    raise ValueError(f"Invalid terminal rule {rule.rule_id}")
            elif rule.classification is not None:
                raise ValueError(f"Non-terminal rule {rule.rule_id} cannot classify")


def load_policy_config(path: Path) -> PolicyDecisionConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))["policy_decision"]
        rules = tuple(RuleConfig(**rule) for rule in raw.pop("rules"))
        return PolicyDecisionConfig(rules=rules, **raw)
    except (KeyError, OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        raise ValueError(
            f"Invalid Policy Decision configuration {path}: {exc}"
        ) from exc
