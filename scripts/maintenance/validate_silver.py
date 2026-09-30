"""Reproducible real-data validation; never use the project's warehouse."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path

from sod_platform.bronze.ingestion.config import load_sources
from sod_platform.bronze.ingestion.spark import create_spark_session
from sod_platform.bronze.pipeline import run_bronze
from sod_platform.silver.contract import INPUT_SCHEMAS
from sod_platform.silver.pipeline import run_silver


def validate(spark, root):
    bronze = run_bronze(spark, load_sources(root / "configs/sources.yml"), root)
    assert bronze["files_failed"] == 0
    first = run_silver(spark, root / "configs/data_quality.yml", date(2025, 2, 1))
    second = run_silver(spark, root / "configs/data_quality.yml", date(2025, 2, 1))
    assert first["rows_written"] == second["rows_written"]
    assert first["quarantined"] == second["quarantined"]
    assert set(first["rows_written"]) == set(INPUT_SCHEMAS)
    assert first["input_records"] == first["valid_records"] + first["quarantined"]
    for name, schema in INPUT_SCHEMAS.items():
        actual = dict(spark.table(f"sod.silver.{name}").dtypes)
        assert all(actual[c] == dtype for c, dtype in schema.items() if c in actual), (
            name
        )
    context = spark.table("sod.silver.access_context")
    assert context.count() == first["rows_written"]["iga_access_assignments"]
    assert len(context.columns) == len(set(context.columns))
    assert (
        context.select("identidade_id", "entitlement_id").distinct().count()
        == context.count()
    )
    requests = spark.table("sod.silver.iga_access_requests")
    statuses = {
        r.status_solicitacao: r["count"]
        for r in requests.groupBy("status_solicitacao").count().collect()
    }
    assert statuses.get("PENDING", 0) > 0 and statuses.get("REJECTED", 0) > 0
    certifications_pending = (
        spark.table("sod.silver.access_certifications")
        .where("decisao='PENDING'")
        .count()
    )
    assert certifications_pending > 0
    unlinked_service_accounts = (
        spark.table("sod.silver.identity_directory")
        .where("tipo_conta='service' AND identidade_id IS NULL")
        .count()
    )
    assert unlinked_service_accounts > 0
    return {
        "spark_master": spark.sparkContext.master,
        "spark_version": spark.version,
        "bronze": bronze,
        "silver_first": first,
        "silver_replay": second,
        "request_statuses": statuses,
        "certifications_pending": certifications_pending,
        "unlinked_service_accounts": unlinked_service_accounts,
        "context_rows": context.count(),
        "context_never_used": context.where("never_used").count(),
        "context_certified": context.where("certification_exists").count(),
    }


def main(report_name="silver-validation.json"):
    root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="sod-silver-validation-") as temporary:
        os.environ["SOD_WAREHOUSE"] = str(Path(temporary) / "warehouse")
        os.environ.setdefault("SPARK_MASTER", "local[2]")
        spark = create_spark_session(root, "sod-silver-validation")
        try:
            report = validate(spark, root)
            target = root / "docs" / report_name
            target.write_text(json.dumps(report, indent=2))
            if report_name != "silver-validation.json":
                (root / "artifacts/validation/silver-validation.json").write_text(
                    json.dumps(report, indent=2)
                )
            print(f"Validated: {target}")
        finally:
            spark.stop()


if __name__ == "__main__":
    main()
