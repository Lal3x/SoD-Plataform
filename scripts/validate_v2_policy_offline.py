"""One independent comparison of frozen PD002 output with V2 labels."""

from __future__ import annotations

import json
from pathlib import Path

from sod_platform.bronze.ingestion.spark import create_spark_session

ROOT = Path(__file__).resolve().parents[1]


def distribution(frame, *columns):
    return [
        {**{column: row[column] for column in columns}, "count": row["count"]}
        for row in frame.groupBy(*columns).count().collect()
    ]


def snapshot(spark, table):
    return str(
        spark.sql(
            f"SELECT snapshot_id FROM {table}.snapshots ORDER BY committed_at DESC LIMIT 1"
        ).first()[0]
    )


def main():
    freeze = json.loads(
        (ROOT / "artifacts/freezes/v2-policy-runtime-freeze.json").read_text()
    )
    assert freeze["freeze"] == "V2 POLICY DECISION FROZEN"
    spark = create_spark_session(ROOT, "sod-v2-policy-offline")
    try:
        assert snapshot(spark, freeze["output_table"]) == freeze["output_snapshot"]
        evidence_freeze = json.loads(
            (
                ROOT / "artifacts/freezes/v2-evidence-1.3.1-runtime-freeze.json"
            ).read_text()
        )
        assert (
            snapshot(spark, evidence_freeze["output_tables"]["summary"])
            == freeze["input_snapshots"]["summary"]
        )
        decisions = spark.table(freeze["output_table"])
        summary = spark.table(evidence_freeze["output_tables"]["summary"])
        gt = spark.read.option("header", True).csv(
            str(ROOT / "tests/fixtures/v2/gabarito.csv")
        )
        assert (
            gt.groupBy("identidade_id", "entitlement_id")
            .count()
            .where("count > 1")
            .limit(1)
            .count()
            == 0
        )
        joined = (
            decisions.join(
                summary.select(
                    "grant_id",
                    "assessment_date",
                    "identidade_id",
                    "entitlement_id",
                    "inherited_access_candidate",
                ),
                ["grant_id", "assessment_date"],
            )
            .join(gt, ["identidade_id", "entitlement_id"], "left")
            .cache()
        )
        assert joined.count() == freeze["output_count"]
        labeled = joined.where("classificacao_esperada IS NOT NULL").cache()
        indevido = labeled.where("classificacao_esperada = 'INDEVIDO'")
        false_safe = indevido.where("policy_decision IN ('PADRAO','LEGITIMO')")
        false_indevido = labeled.where(
            "classificacao_esperada IN ('PADRAO','LEGITIMO') AND policy_decision = 'INDEVIDO'"
        )
        report = {
            "freeze_output_snapshot": freeze["output_snapshot"],
            "labeled": labeled.count(),
            "unlabeled": joined.where("classificacao_esperada IS NULL").count(),
            "gt_policy_matrix": distribution(
                labeled, "classificacao_esperada", "policy_decision"
            ),
            "scenario_policy_matrix": distribution(
                labeled, "cenario", "policy_decision"
            ),
            "padrao_by_birthright": distribution(
                labeled.where("classificacao_esperada = 'PADRAO'"),
                "trusted_birthright",
                "policy_decision",
            ),
            "normal_nonbirthright": distribution(
                labeled.where("cenario = 'normal' AND NOT birthright"),
                "policy_decision",
            ),
            "legitimo_scenarios": distribution(
                labeled.where("classificacao_esperada = 'LEGITIMO'"),
                "cenario",
                "policy_decision",
            ),
            "cross_legitimo_exceptions": [
                r.asDict()
                for r in labeled.where(
                    "cenario LIKE '%cross_legitimo%' AND policy_decision <> 'LEGITIMO'"
                )
                .select(
                    "grant_id",
                    "policy_decision",
                    "policy_rule_id",
                    "certification_status",
                )
                .collect()
            ],
            "inherited_approved": distribution(
                labeled.where(
                    "inherited_access_candidate AND approval_match_strength = 'STRONG_INFERRED'"
                ),
                "policy_decision",
            ),
            "indevido_policy": distribution(indevido, "policy_decision"),
            "critical_false_safe": [
                r.asDict()
                for r in false_safe.select(
                    "grant_id", "policy_decision", "policy_rule_id"
                ).collect()
            ],
            "false_indevido": [
                r.asDict()
                for r in false_indevido.select(
                    "grant_id", "classificacao_esperada", "policy_rule_id"
                ).collect()
            ],
            "unlabeled_policy": distribution(
                joined.where("classificacao_esperada IS NULL"), "policy_decision"
            ),
        }
        assert report["unlabeled"] == 92
        assert indevido.count() == 272
        (ROOT / "artifacts/diagnostics/v2-policy-offline-evaluation.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n"
        )
        print("V2 POLICY OFFLINE EVALUATION COMPLETE", flush=True)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
