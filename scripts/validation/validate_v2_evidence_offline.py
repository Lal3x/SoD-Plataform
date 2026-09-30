"""Read frozen EV001 1.3.1 Evidence and ground truth for diagnostics only."""

from __future__ import annotations

import json
from pathlib import Path

from pyspark.sql import functions as F

from sod_platform.bronze.ingestion.spark import create_spark_session
from sod_platform.common.env import load_project_env

ROOT = Path(__file__).resolve().parents[2]


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
        (ROOT / "artifacts/freezes/v2-evidence-1.3.1-runtime-freeze.json").read_text()
    )
    assert freeze["freeze"] == "V2 EVIDENCE ENGINE EV001 1.3.1 FROZEN"
    load_project_env(ROOT)
    spark = create_spark_session(ROOT, "sod-v2-evidence-offline")
    try:
        assert (
            snapshot(spark, freeze["output_tables"]["summary"])
            == freeze["output_snapshots"]["summary"]
        )
        assert (
            snapshot(spark, freeze["output_tables"]["facts"])
            == freeze["output_snapshots"]["facts"]
        )
        summary = spark.table(freeze["output_tables"]["summary"])
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
        joined = summary.join(gt, ["identidade_id", "entitlement_id"], "left").cache()
        assert joined.count() == freeze["summary_count"]
        labeled = joined.where(F.col("classificacao_esperada").isNotNull()).cache()
        unlabeled = joined.where(F.col("classificacao_esperada").isNull()).count()
        assert unlabeled == 92
        cross = labeled.where(F.col("cenario").contains("cross_legitimo"))
        inherited = labeled.where(F.col("cenario").contains("acesso_herdado"))
        indevido = labeled.where("classificacao_esperada = 'INDEVIDO'")
        cross_total = cross.count()
        indevido_total = indevido.count()
        cross_strong = cross.where(
            "approval_linkage_quality = 'STRONG_INFERRED'"
        ).count()
        indevido_missing = indevido.where(
            "approval_evidence_status = 'NOT_FOUND'"
        ).count()
        report = {
            "freeze_output_snapshots": freeze["output_snapshots"],
            "labeled": labeled.count(),
            "unlabeled": unlabeled,
            "gt_distribution": distribution(labeled, "classificacao_esperada"),
            "gt_evidence_matrix": distribution(
                labeled,
                "classificacao_esperada",
                "expected_access_status",
                "approval_evidence_status",
                "certification_decision",
            ),
            "gt_certification_profile": distribution(
                labeled, "classificacao_esperada", "certification_status"
            ),
            "scenario_evidence": distribution(
                labeled,
                "cenario",
                "classificacao_esperada",
                "expected_access_status",
                "approval_evidence_status",
                "community_relation",
                "public_application",
            ),
            "padrao": distribution(
                labeled.where("classificacao_esperada = 'PADRAO'"),
                "explicit_anchor_flag",
                "expected_access_status",
                "approval_evidence_status",
                "certification_decision",
            ),
            "legitimo": distribution(
                labeled.where("classificacao_esperada = 'LEGITIMO'"),
                "cenario",
                "approval_evidence_status",
                "inherited_access_candidate",
                "public_application",
            ),
            "cross_legitimo": {
                "strong_inferred": cross_strong,
                "total": cross_total,
                "rate": cross_strong / cross_total if cross_total else None,
            },
            "inherited": {
                "total": inherited.count(),
                "predates_current_community": inherited.where(
                    "inherited_access_candidate"
                ).count(),
                "with_strong_approval": inherited.where(
                    "approval_linkage_quality = 'STRONG_INFERRED'"
                ).count(),
                "both": inherited.where(
                    "inherited_access_candidate AND approval_linkage_quality = 'STRONG_INFERRED'"
                ).count(),
            },
            "indevido": {
                "total": indevido_total,
                "approval_not_found": indevido_missing,
                "approval_not_found_rate": (
                    indevido_missing / indevido_total if indevido_total else None
                ),
                "evidence_profile": distribution(
                    indevido,
                    "cenario",
                    "expected_access_status",
                    "community_relation",
                    "public_application",
                    "approval_evidence_status",
                    "certification_decision",
                    "identity_type",
                ),
            },
            "cross_sem_aprovacao": distribution(
                labeled.where(F.col("cenario").contains("cross_sem_aprovacao")),
                "community_relation",
                "public_application",
                "approval_evidence_status",
            ),
            "contractor": distribution(
                labeled.where(F.col("cenario").contains("contractor")),
                "identity_type",
                "community_relation",
                "public_application",
                "approval_evidence_status",
            ),
            "tecnologia_negocio": distribution(
                labeled.where(F.col("cenario").contains("tecnologia")),
                "identity_community",
                "owner_community",
                "public_application",
                "approval_evidence_status",
            ),
        }
        output = (
            ROOT / "artifacts/diagnostics/v2-evidence-1.3.1-offline-diagnostic.json"
        )
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print("V2 EVIDENCE OFFLINE DIAGNOSTIC", output, flush=True)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
