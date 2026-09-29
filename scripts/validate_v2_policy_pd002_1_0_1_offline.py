"""One offline comparison after PD002 1.0.1 runtime freeze."""

from __future__ import annotations

import json
from pathlib import Path

from sod_platform.bronze.ingestion.spark import create_spark_session

ROOT = Path(__file__).resolve().parents[1]


def snapshot(spark, table):
    return str(
        spark.sql(
            f"SELECT snapshot_id FROM {table}.snapshots ORDER BY committed_at DESC LIMIT 1"
        ).first()[0]
    )


def distribution(frame, *columns):
    return [
        {**{column: row[column] for column in columns}, "count": row["count"]}
        for row in frame.groupBy(*columns).count().collect()
    ]


def main():
    freeze = json.loads(
        (
            ROOT / "artifacts/freezes/v2-policy-pd002-1.0.1-runtime-freeze.json"
        ).read_text()
    )
    assert freeze["freeze"] == "V2 POLICY PD002 1.0.1 FROZEN"
    spark = create_spark_session(ROOT, "sod-v2-policy-pd002-1-0-1-offline")
    try:
        assert snapshot(spark, freeze["output_table"]) == freeze["output_snapshot"]
        assert (
            snapshot(spark, freeze["input_tables"]["summary"])
            == freeze["input_snapshots"]["summary"]
        )
        decisions = spark.table(freeze["output_table"])
        summary = spark.table(freeze["input_tables"]["summary"])
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
                    "grant_id", "assessment_date", "identidade_id", "entitlement_id"
                ),
                ["grant_id", "assessment_date"],
            )
            .join(gt, ["identidade_id", "entitlement_id"], "left")
            .cache()
        )
        assert joined.count() == freeze["output_count"]
        labeled = joined.where("classificacao_esperada IS NOT NULL")
        indevido = labeled.where("classificacao_esperada = 'INDEVIDO'")
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
            "legitimo_scenarios": distribution(
                labeled.where("classificacao_esperada = 'LEGITIMO'"),
                "cenario",
                "policy_decision",
            ),
            "indevido_policy": distribution(indevido, "policy_decision"),
            "critical_false_safe": indevido.where(
                "policy_decision IN ('PADRAO', 'LEGITIMO')"
            ).count(),
            "gt_padrao_to_indevido": labeled.where(
                "classificacao_esperada = 'PADRAO' AND policy_decision = 'INDEVIDO'"
            ).count(),
            "gt_legitimo_to_indevido": labeled.where(
                "classificacao_esperada = 'LEGITIMO' AND policy_decision = 'INDEVIDO'"
            ).count(),
        }
        assert report["unlabeled"] == 92
        assert indevido.count() == 272
        (
            ROOT / "artifacts/diagnostics/v2-policy-pd002-1.0.1-offline-evaluation.json"
        ).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print("V2 POLICY PD002 1.0.1 OFFLINE EVALUATION COMPLETE", flush=True)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
