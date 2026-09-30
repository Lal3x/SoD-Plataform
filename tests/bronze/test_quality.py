import logging

import pytest

from sod_platform.bronze.ingestion.spark import (
    SparkPrerequisiteError,
    validate_java_runtime,
)
from sod_platform.bronze.maintenance import (
    UnsafeWarehousePath,
    clean_iceberg_warehouse,
)
from sod_platform.observability.logging import configure_logging
from sod_platform.observability.metrics import BatchMetrics


def test_batch_metrics_cover_ingestion_quality_questions() -> None:
    metrics = BatchMetrics(
        batch_id="batch-1",
        files_discovered=2,
        files_processed=1,
        files_skipped=1,
        records_received=25,
        records_written=25,
        duration_seconds=1.25,
    )

    assert metrics.as_dict()["records_received"] == 25
    assert metrics.as_dict()["duration_seconds"] == 1.25
    assert metrics.as_dict()["files_skipped"] == 1


def test_operational_log_is_persisted(tmp_path) -> None:
    log_file = tmp_path / "logs" / "bronze.log"
    logger = configure_logging(log_file, logging.INFO)
    logger.info("file_failed batch_id=batch-1 ingestion_id=run-1")
    for handler in logger.handlers:
        handler.flush()

    assert "batch_id=batch-1 ingestion_id=run-1" in log_file.read_text()
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()


def test_clean_iceberg_warehouse_removes_generated_data(tmp_path) -> None:
    warehouse = tmp_path / "iceberg-warehouse"
    table_data = warehouse / "bronze" / "identities" / "metadata" / "v1.metadata.json"
    table_data.parent.mkdir(parents=True)
    table_data.write_text("metadata")

    result = clean_iceberg_warehouse(warehouse)

    assert result.deleted_entries == 4
    assert result.warehouse == warehouse
    assert not table_data.exists()
    assert (warehouse / "bronze").is_dir()
    assert (warehouse / "spec").is_dir()


def test_clean_iceberg_warehouse_rejects_non_warehouse_paths(tmp_path) -> None:
    with pytest.raises(UnsafeWarehousePath):
        clean_iceberg_warehouse(tmp_path / "important-data")

    with pytest.raises(UnsafeWarehousePath, match="local filesystem"):
        clean_iceberg_warehouse("s3://bucket/iceberg-warehouse")


def test_missing_java_reports_supported_spark_versions(monkeypatch) -> None:
    monkeypatch.delenv("JAVA_HOME", raising=False)
    monkeypatch.setattr(
        "sod_platform.bronze.ingestion.spark.shutil.which", lambda _: None
    )

    with pytest.raises(SparkPrerequisiteError, match="Java 17 or 21"):
        validate_java_runtime()
