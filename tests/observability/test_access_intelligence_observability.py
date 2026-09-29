from datetime import date
from pathlib import Path

from sod_platform.access_intelligence.pipeline import OUTPUTS, run_access_intelligence


def test_access_intelligence_persists_component_metrics_using_silver_run_id(
    spark, tmp_path: Path
):
    context = spark.createDataFrame(
        [
            (
                "G1",
                "silver-run-1",
                date(2025, 2, 1),
                date(2024, 1, 1),
                "I1",
                "E1",
                "Credito",
                "S1",
                "Analista",
                "employee",
                "active",
                True,
                False,
                False,
                None,
                False,
                "s1",
            ),
            (
                "G2",
                "silver-run-1",
                date(2025, 2, 1),
                date(2024, 1, 1),
                "I2",
                "E1",
                "Credito",
                "S1",
                "Analista",
                "employee",
                "active",
                True,
                False,
                False,
                None,
                False,
                "s1",
            ),
            (
                "G3",
                "silver-run-1",
                date(2025, 2, 1),
                date(2024, 1, 1),
                "I3",
                "E1",
                "Credito",
                "S2",
                "Analista",
                "employee",
                "active",
                False,
                False,
                False,
                None,
                False,
                "s1",
            ),
        ],
        "grant_id string, _silver_run_id string, assessment_date date, data_concessao date, identidade_id string, entitlement_id string, comunidade string, squad string, cargo string, tipo_identidade string, status_identidade string, birthright boolean, cross_community boolean, sigla_publica boolean, certification_decisao string, data_quality_blocking boolean, source_snapshot_id string",
    )
    spark.sql("CREATE NAMESPACE IF NOT EXISTS sod.silver")
    context.writeTo("sod.silver.access_context").using("iceberg").create()
    result = run_access_intelligence(spark, Path("configs/access_intelligence.yml"))

    assert result["run_id"] == "silver-run-1"
    assert result["hard_trusted_set"] == {
        "evaluated": 3,
        "trusted": 2,
        "excluded": 1,
        "trusted_rate": 2 / 3,
        "reason_codes": {
            "TRUSTED_BIRTHRIGHT_ANCHOR": 2,
            "EXCLUDED_NOT_EXPLICIT_ANCHOR": 1,
        },
    }
    assert result["hierarchical_fallback"]["grants_evaluated"] == 3
    assert result["hierarchical_fallback"]["insufficient_evidence"] == 0
    assert result["hierarchical_fallback"]["funnel_by_level"][
        "SQUAD_CARGO_TIPO_IDENTIDADE"
    ] == {
        "evaluated": 3,
        "sufficient": 2,
        "insufficient": 1,
        "selected": 2,
        "fallback_to_next": 1,
    }
    assert result["hierarchical_fallback"]["rejection_reason_by_level"][
        "SQUAD_CARGO_TIPO_IDENTIDADE"
    ] == {
        "INSUFFICIENT_ANALYTICAL_SUPPORT": 1,
    }
    assert result["expected_access"]["evaluated_grants"] == 3
    assert result["expected_access"]["EXPECTED_count"] == 3
    assert result["expected_access"]["expected_from_explicit_anchor"] == 2
    assert result["expected_access"]["expected_from_observed_pattern"] == 1
    assert all(spark.catalog.tableExists(table) for table in OUTPUTS.values())
    audit = spark.table("sod.metadata.access_intelligence_runs")
    assert audit.where("run_id = 'silver-run-1' AND status = 'success'").count() == 4
