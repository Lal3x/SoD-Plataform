from datetime import date

import pytest
from pyspark.sql import functions as F

from sod_platform.access_intelligence.baseline.observed import build_observed_baseline


def _trusted_grants(spark):
    return spark.createDataFrame(
        [
            (
                "G1",
                "I1",
                "E1",
                "Credito",
                "S1",
                "Analista",
                "employee",
                date(2024, 1, 1),
                True,
                "active",
                False,
                False,
                "s1",
            ),
            (
                "G2",
                "I1",
                "E2",
                "Credito",
                "S1",
                "Analista",
                "employee",
                date(2024, 1, 1),
                True,
                "active",
                False,
                False,
                "s1",
            ),
            (
                "G3",
                "I2",
                "E1",
                "Credito",
                "S1",
                "Analista",
                "employee",
                date(2024, 1, 1),
                True,
                "active",
                False,
                False,
                "s2",
            ),
            (
                "G4",
                "I3",
                "E2",
                "Credito",
                "S2",
                "Gerente",
                "contractor",
                date(2024, 1, 1),
                True,
                "active",
                False,
                False,
                "s3",
            ),
            (
                "G5",
                "I4",
                "E3",
                "Inovacao",
                "S3",
                "Analista",
                "employee",
                date(2024, 1, 1),
                True,
                "active",
                False,
                False,
                "s4",
            ),
            (
                "G6",
                "I5",
                "E1",
                "Inovacao",
                "S3",
                "Analista",
                "employee",
                date(2026, 1, 1),
                True,
                "active",
                False,
                False,
                "future",
            ),
            # Non-anchor grants still contribute to observed statistics.
            (
                "G7",
                "I6",
                "E1",
                "Credito",
                "S1",
                "Analista",
                "employee",
                date(2024, 1, 1),
                False,
                "active",
                False,
                False,
                "observed",
            ),
            # Exception/DQ/inactive paths do not redefine the baseline.
            (
                "G8",
                "I7",
                "E1",
                "Credito",
                "S1",
                "Analista",
                "employee",
                date(2024, 1, 1),
                False,
                "active",
                True,
                False,
                "cross",
            ),
            (
                "G9",
                "I8",
                "E1",
                "Credito",
                "S1",
                "Analista",
                "employee",
                date(2024, 1, 1),
                False,
                "active",
                False,
                True,
                "dq",
            ),
            (
                "G10",
                "I9",
                "E1",
                "Credito",
                "S1",
                "Analista",
                "employee",
                date(2024, 1, 1),
                False,
                "inactive",
                False,
                False,
                "inactive",
            ),
        ],
        "grant_id string, identidade_id string, entitlement_id string, comunidade string, squad string, cargo string, tipo_identidade string, data_concessao date, hard_trusted_flag boolean, status_identidade string, cross_community boolean, data_quality_blocking boolean, source_snapshot_id string",
    ).withColumn("assessment_date", F.lit(date(2025, 2, 1)))


def test_observed_baseline_uses_distinct_observable_identities_and_levels(spark):
    rows = build_observed_baseline(_trusted_grants(spark)).collect()
    by_key = {(r.baseline_level, r.entitlement_id): r for r in rows}

    squad_e1 = by_key[("SQUAD_CARGO_TIPO_IDENTIDADE", "E1")]
    assert (squad_e1.population_size, squad_e1.support_count, squad_e1.prevalence) == (
        3,
        3,
        1.0,
    )
    squad_e2 = next(
        row
        for row in rows
        if row.baseline_level == "SQUAD_CARGO_TIPO_IDENTIDADE"
        and row.comunidade == "Credito"
        and row.squad == "S1"
        and row.entitlement_id == "E2"
    )
    assert squad_e2.prevalence == pytest.approx(1 / 3)
    community_e1 = by_key[("COMUNIDADE", "E1")]
    assert (community_e1.population_size, community_e1.support_count) == (4, 3)
    assert community_e1.prevalence == pytest.approx(3 / 4)
    inovacao_e3 = next(
        row
        for row in rows
        if row.baseline_level == "COMUNIDADE"
        and row.comunidade == "Inovacao"
        and row.entitlement_id == "E3"
    )
    assert (inovacao_e3.population_size, inovacao_e3.support_count) == (1, 1)
    comparable_e1 = next(
        row
        for row in rows
        if row.baseline_level == "POPULACAO_COMPARAVEL"
        and row.tipo_identidade == "employee"
        and row.entitlement_id == "E1"
    )
    assert (comparable_e1.population_size, comparable_e1.support_count) == (4, 3)
    assert {row.baseline_version for row in rows} == {"2.0.0"}
    assert all(row.baseline_timestamp is not None for row in rows)


def test_observed_baseline_requires_observable_population_contract(spark):
    with pytest.raises(ValueError, match="status_identidade"):
        build_observed_baseline(spark.createDataFrame([("G1",)], "grant_id string"))


def test_empty_explicit_anchor_set_does_not_zero_observed_population(spark):
    rows = build_observed_baseline(
        _trusted_grants(spark).withColumn("hard_trusted_flag", F.lit(False))
    )
    assert (
        rows.where("baseline_level = 'COMUNIDADE' AND comunidade = 'Credito'").count()
        > 0
    )


def test_baseline_is_deterministic_and_counts_each_holder_once(spark):
    access = _trusted_grants(spark)
    duplicate = access.where("grant_id = 'G1'").withColumn("grant_id", F.lit("G1-copy"))
    repeated = access.unionByName(duplicate)
    first = build_observed_baseline(repeated)
    second = build_observed_baseline(repeated.repartition(3))
    keys = [
        "assessment_date",
        "baseline_level",
        "comunidade",
        "squad",
        "cargo",
        "tipo_identidade",
        "entitlement_id",
        "population_size",
        "support_count",
        "prevalence",
        "baseline_version",
        "source_snapshot_id",
    ]
    assert first.select(*keys).exceptAll(second.select(*keys)).count() == 0
    assert second.select(*keys).exceptAll(first.select(*keys)).count() == 0
    row = first.where(
        "baseline_level = 'SQUAD_CARGO_TIPO_IDENTIDADE' AND entitlement_id = 'E1' AND comunidade = 'Credito'"
    ).first()
    assert (row.population_size, row.support_count, row.prevalence) == (3, 3, 1.0)
