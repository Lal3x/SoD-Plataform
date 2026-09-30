"""Offline label diagnostics for the frozen V2 Expected Access snapshot."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from sod_platform.bronze.ingestion.spark import create_spark_session
from sod_platform.common.env import load_project_env

ROOT = Path(__file__).resolve().parents[2]
STATES = ("EXPECTED", "UNEXPECTED", "INSUFFICIENT_EVIDENCE")


def state_counts(frame):
    counts = frame.expected_access_status.value_counts()
    return {state: int(counts.get(state, 0)) for state in STATES}


def main():
    freeze = json.loads(
        (ROOT / "artifacts/freezes/v2-expected-access-runtime-freeze.json").read_text()
    )
    assert freeze["freeze"] == "V2 EXPECTED ACCESS FROZEN"
    load_project_env(ROOT)
    spark = create_spark_session(ROOT, "sod-v2-expected-access-offline")
    try:
        context = spark.table("sod.silver.access_context")
        hts = spark.table("sod.access_intelligence.hard_trusted_set")
        fallback = spark.table("sod.access_intelligence.hierarchical_fallback")
        ea = spark.table("sod.access_intelligence.expected_access")
        fields = [
            "grant_id",
            "identidade_id",
            "entitlement_id",
            "sigla_id",
            "comunidade",
            "squad",
            "cargo",
            "tipo_identidade",
            "comunidade_dona_sigla",
            "cross_community",
            "sigla_publica",
            "birthright",
            "approval_relevance",
            "certification_decisao",
            "status_identidade",
            "data_quality_blocking",
            "data_concessao",
            "assessment_date",
        ]
        joined = (
            context.select(*fields)
            .join(
                hts.select("grant_id", "hard_trusted_flag", "hard_trusted_reason"),
                "grant_id",
            )
            .join(
                ea.select(
                    "grant_id",
                    "expected_access_status",
                    "expected_access_reason",
                    "selected_baseline_level",
                    "population_size",
                    "support_count",
                    "prevalence",
                    "expectation_evidence_strength",
                ),
                "grant_id",
            )
            .join(fallback.select("grant_id", "fallback_reason"), "grant_id")
        )
        data = joined.toPandas()
        assert len(data) == freeze["total_grants"] and data.grant_id.is_unique
    finally:
        spark.stop()
    comparable_holder = (
        ~data.cross_community.fillna(True)
        & ~data.data_quality_blocking.fillna(True)
        & data.status_identidade.str.lower().eq("active")
        & data.data_concessao.notna()
        & (data.data_concessao <= data.assessment_date)
    )
    comparable_id_types = set(
        zip(
            data.loc[comparable_holder, "identidade_id"],
            data.loc[comparable_holder, "tipo_identidade"],
        )
    )
    population_member = comparable_holder | (
        data.selected_baseline_level.eq("POPULACAO_COMPARAVEL")
        & pd.Series(
            list(zip(data.identidade_id, data.tipo_identidade)), index=data.index
        ).isin(comparable_id_types)
    )
    loo_population = data.population_size - population_member.astype(int)
    loo_support = data.support_count - comparable_holder.astype(int)
    data["loo_prevalence"] = (loo_support / loo_population).where(loo_population > 0)
    labels = pd.read_csv(ROOT / "tests/fixtures/v2/gabarito.csv")
    assert not labels[["identidade_id", "entitlement_id"]].duplicated().any()
    matched = data.merge(
        labels,
        on=["identidade_id", "entitlement_id"],
        how="left",
        validate="one_to_one",
    )
    unlabeled = matched.classificacao_esperada.isna()
    evaluated = matched.loc[~unlabeled].copy()
    normal = evaluated[
        (evaluated.cenario == "normal")
        & ~evaluated.birthright
        & ~evaluated.sigla_publica
    ]
    birthrights = evaluated[evaluated.birthright]
    conflicts = evaluated[
        evaluated.hard_trusted_reason == "EXCLUDED_EXPLICIT_CONTRADICTION"
    ]
    legitimate = evaluated[evaluated.classificacao_esperada == "LEGITIMO"]
    improper = evaluated[evaluated.classificacao_esperada == "INDEVIDO"]
    collisions = improper[improper.expected_access_status == "EXPECTED"].copy()
    matrix = pd.crosstab(
        evaluated.classificacao_esperada, evaluated.expected_access_status
    )
    report = {
        "freeze_output_snapshot": freeze["output_snapshot"],
        "total_runtime_grants": len(data),
        "offline_labeled_grants": len(evaluated),
        "unlabeled_runtime_grants": int(unlabeled.sum()),
        "unlabeled_state_counts": state_counts(matched.loc[unlabeled]),
        "all_runtime_public_nonbirthright": int(
            (data.sigla_publica & ~data.birthright).sum()
        ),
        "all_runtime_public_birthright": int(
            (data.sigla_publica & data.birthright).sum()
        ),
        "matrix": {
            gt: {
                state: int(matrix.loc[gt, state]) if state in matrix.columns else 0
                for state in STATES
            }
            for gt in matrix.index
        },
        "normal_non_birthright_non_public": len(normal),
        "normal_state_counts": state_counts(normal),
        "normal_loo_ge_80": int((normal.loo_prevalence >= 0.8).sum()),
        "normal_loo_ge_90": int((normal.loo_prevalence >= 0.9).sum()),
        "normal_loo_ge_95": int((normal.loo_prevalence >= 0.95).sum()),
        "birthright_total": len(birthrights),
        "birthright_state_counts": state_counts(birthrights),
        "trusted_birthright_total": int(birthrights.hard_trusted_flag.sum()),
        "trusted_birthright_state_counts": state_counts(
            birthrights[birthrights.hard_trusted_flag]
        ),
        "hts_conflicts_total": len(conflicts),
        "hts_conflict_state_counts": state_counts(conflicts),
        "hts_conflict_reason_counts": conflicts.expected_access_reason.value_counts().to_dict(),
        "legitimate_total": len(legitimate),
        "legitimate_state_counts": state_counts(legitimate),
        "cross_legitimo_state_counts": state_counts(
            evaluated[evaluated.cenario == "cross_legitimo"]
        ),
        "public_nonbirthright_state_counts": state_counts(
            evaluated[evaluated.sigla_publica & ~evaluated.birthright]
        ),
        "improper_total": len(improper),
        "improper_state_counts": state_counts(improper),
        "indevido_expected_collision": len(collisions),
        "no_baseline_fallback_reasons": data.loc[
            data.expected_access_reason.eq("INSUFFICIENT_NO_BASELINE"),
            "fallback_reason",
        ]
        .value_counts()
        .to_dict(),
    }
    out = ROOT / "artifacts/diagnostics/v2-expected-access-offline-metrics.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    collisions[
        [
            "grant_id",
            "cenario",
            "identidade_id",
            "comunidade",
            "squad",
            "cargo",
            "tipo_identidade",
            "entitlement_id",
            "sigla_id",
            "comunidade_dona_sigla",
            "birthright",
            "sigla_publica",
            "cross_community",
            "approval_relevance",
            "selected_baseline_level",
            "population_size",
            "support_count",
            "prevalence",
            "loo_prevalence",
            "expected_access_reason",
        ]
    ].to_csv(
        ROOT / "artifacts/diagnostics/v2-expected-access-indevido-collisions.csv",
        index=False,
    )
    print(
        json.dumps(
            {
                "normal": report["normal_state_counts"],
                "indevido_expected_collision": len(collisions),
                "unlabeled": int(unlabeled.sum()),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
