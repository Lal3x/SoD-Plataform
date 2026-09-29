"""One independent prioritization diagnostic after the RISK001 freeze."""

from __future__ import annotations

import json
from pathlib import Path

from sod_platform.bronze.ingestion.spark import create_spark_session

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/diagnostics/v2-risk-offline-diagnostic.json"


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
    assert not OUTPUT.exists(), (
        "Offline diagnostic already exists; refusing a second evaluation"
    )
    freeze = json.loads(
        (ROOT / "artifacts/freezes/v2-risk-runtime-freeze.json").read_text()
    )
    assert freeze["freeze"] == "V2 RISK RISK001 1.0.0 FROZEN"
    spark = create_spark_session(ROOT, "sod-v2-risk-offline")
    try:
        assert snapshot(spark, freeze["output_table"]) == freeze["output_snapshot"]
        risk = spark.table(freeze["output_table"])
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
        joined = risk.join(gt, ["identidade_id", "entitlement_id"], "left").cache()
        assert joined.count() == freeze["output_count"]
        labeled = joined.where("classificacao_esperada IS NOT NULL")
        indevido = labeled.where("classificacao_esperada = 'INDEVIDO'")
        report = {
            "freeze_output_snapshot": freeze["output_snapshot"],
            "labeled": labeled.count(),
            "unlabeled": joined.where("classificacao_esperada IS NULL").count(),
            "gt_risk_band": distribution(
                labeled, "classificacao_esperada", "risk_band"
            ),
            "gt_policy_action_risk": distribution(
                labeled,
                "classificacao_esperada",
                "policy_decision",
                "priority_action",
                "risk_band",
            ),
            "gt_indevido_risk_band": distribution(indevido, "risk_band"),
            "gt_indevido_count": indevido.count(),
            "unlabeled_risk_band": distribution(
                joined.where("classificacao_esperada IS NULL"), "risk_band"
            ),
        }
        assert report["unlabeled"] == 92
        assert report["gt_indevido_count"] == 272
        OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print("V2 RISK RISK001 1.0.0 OFFLINE DIAGNOSTIC COMPLETE", flush=True)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
