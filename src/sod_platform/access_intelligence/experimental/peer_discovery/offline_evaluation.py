"""Post-freeze ground-truth evaluation; deliberately absent from runtime."""

from pyspark.sql import DataFrame


def evaluate_frozen_peer_shadow(shadow: DataFrame, labels: DataFrame) -> dict:
    """Return offline safety/recovery counts after a model run is frozen.

    Callers must load labels outside production runtime.  This function never
    returns parameters and cannot influence LDA, FP-Growth, or thresholds.
    """
    required = {"grant_id", "assessment_date", "peer_expected_status"}
    label_columns = {"grant_id", "classificacao_esperada"}
    if required - set(shadow.columns) or label_columns - set(labels.columns):
        raise ValueError(
            "Offline evaluation requires frozen shadow and labelled grants"
        )
    evaluated = shadow.join(
        labels.select(
            "grant_id",
            "classificacao_esperada",
            *(["cenario"] if "cenario" in labels.columns else []),
        ),
        "grant_id",
        "inner",
    )
    return {
        "labelled_grants": evaluated.count(),
        "ground_truth_by_peer_status": {
            f"{r['classificacao_esperada']}→{r['peer_expected_status']}": r["count"]
            for r in evaluated.groupBy("classificacao_esperada", "peer_expected_status")
            .count()
            .collect()
        },
        "critical_indev_ido_to_peer_expected": evaluated.where(
            "classificacao_esperada = 'INDEVIDO' AND peer_expected_status = 'PEER_EXPECTED'"
        )
        .select("grant_id")
        .orderBy("grant_id")
        .collect(),
        "normal_peer_expected": (
            evaluated.where(
                "cenario = 'normal' AND peer_expected_status = 'PEER_EXPECTED'"
            ).count()
            if "cenario" in evaluated.columns
            else None
        ),
    }
