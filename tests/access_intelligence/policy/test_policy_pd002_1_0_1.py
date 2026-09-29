"""Synthetic PD002 1.0.1 rule and collision contracts, independent of labels."""

from datetime import date
from pathlib import Path

from sod_platform.access_intelligence.policy.rules import build_pd002, load_catalog

CATALOG = (
    Path(__file__).resolve().parents[3] / "configs/policy_decision_pd002_1_0_1.yml"
)
SCHEMA = """grant_id string, assessment_date date, evidence_bundle_id string,
evidence_bundle_method_id string, evidence_bundle_version string,
evidence_ids array<string>, data_quality_blocking boolean, community_relation string,
public_application boolean, birthright boolean, explicit_anchor_flag boolean,
identity_type string,
approval_evidence_status string, approval_linkage_quality string,
approval_relevance string, approval_candidate_count long, request_source_coverage string,
certification_status string, expected_access_status string,
expectation_evidence_strength string, population_size long, support_count long,
prevalence double, selected_baseline_level string, baseline_version string,
contradiction_codes array<string>, approval_effective_at date,
certification_date date"""
FIELDS = [part.strip().split()[0] for part in SCHEMA.split(",")]
BASE = {
    "grant_id": "base",
    "assessment_date": date(2025, 2, 1),
    "evidence_bundle_id": "bundle",
    "evidence_bundle_method_id": "EV001",
    "evidence_bundle_version": "1.3.1",
    "evidence_ids": ["e1"],
    "data_quality_blocking": False,
    "community_relation": "SAME_COMMUNITY",
    "public_application": False,
    "birthright": False,
    "explicit_anchor_flag": False,
    "identity_type": "EMPLOYEE",
    "approval_evidence_status": "NOT_FOUND",
    "approval_linkage_quality": "UNKNOWN",
    "approval_relevance": "NOT_FOUND",
    "approval_candidate_count": 0,
    "request_source_coverage": "AUTHORITATIVE_FOR_V2",
    "certification_status": "CERTIFICATION_NOT_FOUND",
    "expected_access_status": "UNEXPECTED",
    "expectation_evidence_strength": "LOW",
    "population_size": 0,
    "support_count": 0,
    "prevalence": None,
    "selected_baseline_level": None,
    "baseline_version": None,
    "contradiction_codes": [],
    "approval_effective_at": None,
    "certification_date": None,
}
STRONG = {
    "approval_evidence_status": "UNIQUE_MATCH",
    "approval_linkage_quality": "STRONG_INFERRED",
    "approval_relevance": "UNCERTAIN",
    "approval_candidate_count": 1,
}
CROSS = {"community_relation": "CROSS_COMMUNITY"}
REVOKE = {"certification_status": "REVOKE"}
RELIABLE = {
    "expected_access_status": "EXPECTED",
    "expectation_evidence_strength": "HIGH",
    "population_size": 50,
    "support_count": 40,
    "prevalence": 0.8,
    "selected_baseline_level": "COMMUNITY",
    "baseline_version": "1.0.0",
}


def test_every_terminal_rule_and_collisions(spark):
    cases = [
        ("R010", "REVISAO", dict(data_quality_blocking=True, **STRONG)),
        ("R025", "REVISAO", dict(**CROSS, **STRONG, **REVOKE)),
        ("R020", "LEGITIMO", dict(**CROSS, **STRONG)),
        ("R030", "INDEVIDO", dict(**CROSS)),
        ("R040", "REVISAO", REVOKE),
        ("R050", "PADRAO", {"birthright": True, "explicit_anchor_flag": True}),
        ("R060", "PADRAO", RELIABLE),
        ("R070", "LEGITIMO", STRONG),
        ("R080", "LEGITIMO", {"public_application": True}),
        ("R110", "REVISAO", {"approval_evidence_status": "NOT_FOUND"}),
        ("R120", "REVISAO", {"expected_access_status": "INSUFFICIENT_EVIDENCE"}),
        ("R130", "REVISAO", dict(**CROSS, request_source_coverage="UNKNOWN")),
        (
            "R140",
            "REVISAO",
            {
                "approval_evidence_status": "MULTIPLE_CANDIDATES",
                "approval_linkage_quality": "AMBIGUOUS",
                "approval_candidate_count": 2,
            },
        ),
        ("R999", "REVISAO", {"expected_access_status": "UNKNOWN"}),
        (
            "strong_not_ambiguous",
            "R070",
            "LEGITIMO",
            dict(**STRONG, approval_effective_at=date(2024, 1, 1)),
        ),
        ("strong_revoke", "R040", "REVISAO", dict(**STRONG, **REVOKE)),
        ("cross_strong", "R020", "LEGITIMO", dict(**CROSS, **STRONG)),
        (
            "ambiguous_not_r070",
            "R140",
            "REVISAO",
            {
                "approval_evidence_status": "MULTIPLE_CANDIDATES",
                "approval_linkage_quality": "AMBIGUOUS",
                "approval_candidate_count": 2,
                "approval_relevance": "UNCERTAIN",
            },
        ),
        ("cross_expected_not_standard", "R030", "INDEVIDO", dict(**CROSS, **RELIABLE)),
        (
            "not_found_weak_coverage",
            "R130",
            "REVISAO",
            dict(**CROSS, request_source_coverage="UNKNOWN"),
        ),
        (
            "maintain_not_legitimate",
            "R110",
            "REVISAO",
            {"certification_status": "MAINTAIN"},
        ),
        ("contractor_not_indevido", "R110", "REVISAO", {"identity_type": "CONTRACTOR"}),
    ]
    rows = []
    expected = {}
    for item in cases:
        if len(item) == 3:
            rule, decision, overrides = item
            name = rule
        else:
            name, rule, decision, overrides = item
        row = {**BASE, **overrides, "grant_id": name}
        rows.append(tuple(row[field] for field in FIELDS))
        expected[name] = (rule, decision)
    frame = spark.createDataFrame(rows, SCHEMA)
    actual = {
        r.grant_id: (r.policy_rule_id, r.policy_decision)
        for r in build_pd002(frame, load_catalog(CATALOG)).collect()
    }
    assert actual == expected
