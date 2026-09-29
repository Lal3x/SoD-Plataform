"""Metadata schema and ingestion run audit writes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pyspark.sql import SparkSession
from pyspark.sql.types import (
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

RUN_TABLE = "sod.metadata.ingestion_runs"
RUN_SCHEMA = StructType(
    [
        StructField("filename_source_system", StringType(), True),
        StructField("filename_source_name", StringType(), True),
        StructField("filename_extract_timestamp", StringType(), True),
        StructField("file_bytes", LongType(), True),
        StructField("schema_event", StringType(), True),
        StructField("source_batches", StringType(), True),
        StructField("latency_seconds", DoubleType(), True),
        StructField("batch_id", StringType(), False),
        StructField("ingestion_id", StringType(), False),
        StructField("source_name", StringType(), False),
        StructField("target_table", StringType(), False),
        StructField("source_file", StringType(), False),
        StructField("source_file_hash", StringType(), True),
        StructField("started_at", TimestampType(), False),
        StructField("finished_at", TimestampType(), True),
        StructField("duration_seconds", DoubleType(), True),
        StructField("status", StringType(), False),
        StructField("records_received", LongType(), True),
        StructField("records_written", LongType(), True),
        StructField("error_category", StringType(), True),
        StructField("error_type", StringType(), True),
        StructField("error_message", StringType(), True),
    ]
)


def ensure_namespace(spark: SparkSession, namespace: str) -> None:
    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {namespace}")


def write_run(spark: SparkSession, record: dict[str, Any]) -> None:
    """Append an audit record to the Iceberg control table."""
    ensure_namespace(spark, "sod.metadata")
    frame = spark.createDataFrame([record], schema=RUN_SCHEMA)
    if spark.catalog.tableExists(RUN_TABLE):
        frame.writeTo(RUN_TABLE).append()
    else:
        frame.writeTo(RUN_TABLE).using("iceberg").create()


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp for Spark's TimestampType."""
    return datetime.now(UTC)


EXECUTION_TABLE = "sod.metadata.bronze_executions"
EXECUTION_SCHEMA = StructType(
    [
        StructField("batch_id", StringType(), False),
        StructField("source_name", StringType(), False),
        StructField("status", StringType(), False),
        StructField("started_at", TimestampType(), False),
        StructField("finished_at", TimestampType(), True),
        StructField("metrics_json", StringType(), False),
    ]
)


def write_execution(spark, record):
    frame = spark.createDataFrame([record], EXECUTION_SCHEMA)
    if spark.catalog.tableExists(EXECUTION_TABLE):
        frame.writeTo(EXECUTION_TABLE).append()
    else:
        frame.writeTo(EXECUTION_TABLE).using("iceberg").create()


def write_quarantine(spark, record):
    table = "sod.metadata.bronze_quarantine"
    frame = spark.createDataFrame([record], RUN_SCHEMA)
    if spark.catalog.tableExists(table):
        frame.writeTo(table).append()
    else:
        frame.writeTo(table).using("iceberg").create()


def write_runs(spark, records, table=RUN_TABLE):
    """Commit file audit events together, retaining one row per attempt."""
    if not records:
        return
    frame = spark.createDataFrame(records, RUN_SCHEMA)
    if spark.catalog.tableExists(table):
        frame.writeTo(table).append()
    else:
        frame.writeTo(table).using("iceberg").create()
