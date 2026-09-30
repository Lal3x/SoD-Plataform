from datetime import date
from pathlib import Path

import yaml
from pyspark.sql import Row
from pyspark.sql import functions as F

from sod_platform.silver.pipeline import run_silver
from sod_platform.silver.quality.validation import validate_with_gx
from sod_platform.silver.transform import normalize_strings, parse_date


def test_community_normalization_and_original_value(spark):
    df = spark.createDataFrame([Row(comunidade=" CREDITO "), Row(comunidade="Credito")])
    rows = normalize_strings(df).collect()
    assert [row.comunidade for row in rows] == ["Credito", "Credito"]
    assert rows[0].comunidade_original == " CREDITO "


def test_date_formats_and_nullable_value(spark):
    df = spark.createDataFrame([("2024-01-02",), ("03/01/2024",), (None,)], ["dt"])
    rows = parse_date(df, "dt", ["yyyy-MM-dd", "dd/MM/yyyy"]).collect()
    assert [row.dt for row in rows] == [date(2024, 1, 2), date(2024, 1, 3), None]


def test_great_expectations_runs_on_spark_dataframe(spark):
    df = spark.createDataFrame(
        [("ID-1", "employee")], ["identidade_id", "tipo_identidade"]
    )
    df = df.withColumn("comunidade", F.lit("Credito")).withColumn(
        "data_entrada_comunidade_atual", F.lit(None).cast("date")
    )
    results = validate_with_gx("identities", df, {"tipo_identidade": ["employee"]})
    assert len(results) == 5
    assert all(item["success"] for item in results)


def test_silver_pipeline_quarantine_and_idempotent_snapshots(spark, tmp_path: Path):
    suffix = "silver_test"
    tables = {
        name: f"sod.bronze.{suffix}_{name}"
        for name in ("identities", "entitlements", "accesses", "approvals")
    }
    inputs = {
        "identities": [
            ("ID-1", " CREDITO ", "employee", None, "squad", "cargo", "gestor")
        ],
        "entitlements": [
            ("ENT-1", "SIG-1", "credito", "true", "false", "HIGH", "false")
        ],
        "accesses": [
            ("ID-1", "ENT-1", "2024-01-02", "detectado", None),
            ("ID-1", "ENT-1", "2024-01-02", "detectado", None),
            ("NO-ID", "ENT-1", "2024-01-03", "atribuido", None),
        ],
        "approvals": [("ID-1", "ENT-1", "2024-01-02", "GESTOR-1")],
    }
    schemas = {
        "identities": "identidade_id string, comunidade string, tipo_identidade string, data_entrada_comunidade_atual string, squad string, cargo string, gestor string",
        "entitlements": "entitlement_id string, sigla_id string, comunidade_dona_sigla string, birthright string, sigla_publica string, criticidade string, privileged string",
        "accesses": "identidade_id string, entitlement_id string, data_concessao string, tipo_atribuicao string, ultimo_uso string",
        "approvals": "identidade_id string, entitlement_id string, data_aprovacao string, aprovador string",
    }
    for name, rows in inputs.items():
        df = spark.createDataFrame(rows, schemas[name])
        df.writeTo(tables[name]).using("iceberg").createOrReplace()

    config_path = tmp_path / "dq.yml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "domains": {
                    "tipo_identidade": ["employee"],
                    "tipo_atribuicao": ["detectado", "atribuido"],
                },
                "date_formats": ["yyyy-MM-dd"],
                "tables": tables,
            }
        ),
        encoding="utf-8",
    )
    first = run_silver(spark, config_path)
    assert spark.table("sod.silver.iga_access_assignments").count() == 1
    assert first["quarantined"] == 2
    second = run_silver(spark, config_path)
    assert spark.table("sod.silver.iga_access_assignments").count() == 1
    assert second["quarantined"] == 2
    audit = spark.table("sod.metadata.silver_runs").where("status <> 'started'")
    assert audit.count() == 2
    assert audit.orderBy(F.desc("started_at")).first()["records_quarantined"] == 2
