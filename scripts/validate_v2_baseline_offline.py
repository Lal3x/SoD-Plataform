"""Offline-only V2 label comparison after the baseline/fallback freeze."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from sod_platform.bronze.ingestion.spark import create_spark_session
from sod_platform.common.env import load_project_env

ROOT = Path(__file__).resolve().parents[1]


def describe(frame, field):
    values = frame[field].dropna()
    return {
        key: float(value)
        for key, value in values.quantile([0, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 1])
        .rename(
            index={
                0: "min",
                0.1: "p10",
                0.25: "p25",
                0.5: "median",
                0.75: "p75",
                0.9: "p90",
                0.95: "p95",
                0.99: "p99",
                1: "max",
            }
        )
        .items()
    }


def threshold_counts(frame, field):
    return {
        str(t): {
            "count": int((frame[field] >= t).sum()),
            "rate": float((frame[field] >= t).mean()),
        }
        for t in (0.8, 0.9, 0.95)
    }


def main():
    freeze_path = (
        ROOT / "artifacts/freezes/v2-observed-baseline-fallback-runtime-freeze.json"
    )
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    assert freeze["freeze"] == "V2 OBSERVED BASELINE + FALLBACK FROZEN"
    load_project_env(ROOT)
    spark = create_spark_session(ROOT, "sod-v2-baseline-offline-validation")
    try:
        context = spark.table("sod.silver.access_context")
        fallback = spark.table("sod.access_intelligence.hierarchical_fallback")
        fields = [
            "grant_id",
            "identidade_id",
            "entitlement_id",
            "comunidade",
            "squad",
            "cargo",
            "tipo_identidade",
            "cross_community",
            "sigla_publica",
            "birthright",
            "approval_relevance",
            "status_identidade",
            "data_quality_blocking",
            "data_concessao",
            "assessment_date",
        ]
        data = (
            context.select(*fields)
            .join(
                fallback.select(
                    "grant_id",
                    "selected_baseline_level",
                    "selected_population_size",
                    "selected_support_count",
                    "selected_prevalence",
                    "baseline_sufficient",
                ),
                "grant_id",
            )
            .toPandas()
        )
        assert len(data) == 75577 and data.grant_id.is_unique
    finally:
        spark.stop()
    comparable_holder = (
        (~data.cross_community.fillna(True))
        & (~data.data_quality_blocking.fillna(True))
        & data.status_identidade.str.lower().eq("active")
        & data.data_concessao.notna()
        & (data.data_concessao <= data.assessment_date)
    )
    # For a cross-community grant, the identity's grant was excluded from the
    # observed support. Removing it again would bias LOO downward.
    comparable_id_types = set(
        zip(
            data.loc[comparable_holder, "identidade_id"],
            data.loc[comparable_holder, "tipo_identidade"],
        )
    )
    population_holder = comparable_holder | (
        data.selected_baseline_level.eq("POPULACAO_COMPARAVEL")
        & pd.Series(
            list(zip(data.identidade_id, data.tipo_identidade)), index=data.index
        ).isin(comparable_id_types)
    )
    data["loo_population"] = data.selected_population_size - population_holder.astype(
        int
    )
    data["loo_support"] = data.selected_support_count - comparable_holder.astype(int)
    data["loo_prevalence"] = (data.loo_support / data.loo_population).where(
        data.loo_population > 0
    )
    labels = pd.read_csv(ROOT / "tests/fixtures/v2/gabarito.csv")
    assert labels[["identidade_id", "entitlement_id"]].duplicated().sum() == 0
    evaluated = data.merge(
        labels,
        on=["identidade_id", "entitlement_id"],
        how="left",
        validate="one_to_one",
    )
    unmatched = evaluated.classificacao_esperada.isna()
    if unmatched.any():
        print(
            "OFFLINE_UNMATCHED_LABELS",
            int(unmatched.sum()),
            evaluated.loc[unmatched, ["identidade_id", "entitlement_id"]]
            .head(5)
            .to_dict("records"),
            flush=True,
        )
    evaluated = evaluated.loc[~unmatched].copy()
    normal = evaluated[
        (evaluated.cenario == "normal")
        & ~evaluated.birthright
        & ~evaluated.sigla_publica
    ]
    birthright_normal = evaluated[
        (evaluated.cenario == "normal") & evaluated.birthright
    ]
    legitimate = evaluated[evaluated.classificacao_esperada == "LEGITIMO"]
    improper = evaluated[evaluated.classificacao_esperada == "INDEVIDO"]
    collisions = improper[
        improper.baseline_sufficient & (improper.selected_prevalence >= 0.8)
    ].copy()
    report = {
        "freeze_file": str(freeze_path.relative_to(ROOT)),
        "evaluated_grants": len(evaluated),
        "unmatched_runtime_grants": int(unmatched.sum()),
        "normal_non_birthright_non_public": len(normal),
        "normal_birthright": len(birthright_normal),
        "normal_prevalence": describe(normal, "selected_prevalence"),
        "normal_loo_prevalence": describe(normal, "loo_prevalence"),
        "normal_population": describe(normal, "selected_population_size"),
        "normal_support": describe(normal, "selected_support_count"),
        "normal_by_level": normal.selected_baseline_level.fillna("INSUFFICIENT")
        .value_counts()
        .to_dict(),
        "normal_identifiability": threshold_counts(
            normal[normal.baseline_sufficient], "selected_prevalence"
        ),
        "normal_loo": threshold_counts(normal, "loo_prevalence"),
        "legitimate_prevalence": describe(legitimate, "selected_prevalence"),
        "improper_prevalence": describe(improper, "selected_prevalence"),
        "high_prevalence_indevido_collision": len(collisions),
        "indevido_collision_thresholds": threshold_counts(
            improper[improper.baseline_sufficient], "selected_prevalence"
        ),
        "gt_by_fallback_level": pd.crosstab(
            evaluated.classificacao_esperada,
            evaluated.selected_baseline_level.fillna("INSUFFICIENT"),
        ).to_dict(orient="index"),
    }
    # Counts above use a reliable-subset denominator; add the eligible denominator explicitly.
    report["normal_identifiability"] = {
        k: {"count": v["count"], "rate": v["count"] / len(normal)}
        for k, v in report["normal_identifiability"].items()
    }
    report["indevido_collision_thresholds"] = {
        k: {"count": v["count"], "rate": v["count"] / len(improper)}
        for k, v in report["indevido_collision_thresholds"].items()
    }
    report["normal_contract_ge_90_pass"] = (
        report["normal_identifiability"]["0.9"]["rate"] >= 0.95
    )
    output = (
        ROOT
        / "artifacts/diagnostics/v2-observed-baseline-fallback-offline-metrics.json"
    )
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    collision_path = (
        ROOT / "artifacts/diagnostics/v2-observed-baseline-indevido-collisions.csv"
    )
    collisions.to_csv(collision_path, index=False)
    print(
        json.dumps(
            {
                "normal_contract_ge_90_pass": report["normal_contract_ge_90_pass"],
                "collisions": len(collisions),
                "normal": len(normal),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
