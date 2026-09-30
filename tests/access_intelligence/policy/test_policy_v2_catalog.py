"""PD002 catalog contract; runtime grain is checked by the materializer."""

from pathlib import Path

import pytest
import yaml

from sod_platform.access_intelligence.policy.rules import load_catalog

CATALOG = Path(__file__).resolve().parents[3] / "configs/policy_decision_pd002.yml"


def test_pd002_precedence_is_explicit_and_complete():
    catalog = load_catalog(CATALOG)
    assert catalog["policy_id"] == "PD002"
    assert [r["id"] for r in catalog["rules"]] == [
        "R010",
        "R025",
        "R020",
        "R030",
        "R040",
        "R140",
        "R050",
        "R060",
        "R070",
        "R080",
        "R110",
        "R120",
        "R130",
        "R999",
    ]


def test_pd002_rejects_reordered_or_duplicate_rules(tmp_path):
    catalog = yaml.safe_load(CATALOG.read_text())
    catalog["rules"][0], catalog["rules"][1] = catalog["rules"][1], catalog["rules"][0]
    path = tmp_path / "reordered.yml"
    path.write_text(yaml.safe_dump(catalog))
    with pytest.raises(ValueError, match="precedence"):
        load_catalog(path)
    catalog["rules"][0] = catalog["rules"][1]
    path.write_text(yaml.safe_dump(catalog))
    with pytest.raises(ValueError, match="precedence"):
        load_catalog(path)


def test_pd002_rejects_invalid_decision(tmp_path):
    catalog = yaml.safe_load(CATALOG.read_text())
    catalog["rules"][0]["decision"] = "POTENCIALMENTE_INDEVIDO"
    path = tmp_path / "invalid.yml"
    path.write_text(yaml.safe_dump(catalog))
    with pytest.raises(ValueError, match="decision"):
        load_catalog(path)
