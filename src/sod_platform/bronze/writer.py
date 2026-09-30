"""Append raw source records and lineage columns to Iceberg tables."""

from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, FloatType, IntegerType, LongType

LINEAGE_COLUMNS = (
    "_ingestion_id",
    "_ingestion_timestamp",
    "_ingestion_date",
    "_source_name",
    "_source_file",
    "_source_file_hash",
)


class SchemaCompatibilityError(RuntimeError):
    """The source schema is incompatible with its Iceberg table."""


def add_lineage(
    data: DataFrame,
    ingestion_id: str,
    source_name: str,
    source_file: str,
    source_file_hash: str,
) -> DataFrame:
    """Add immutable per-record ingestion lineage without changing source fields."""
    collision = set(data.columns).intersection(LINEAGE_COLUMNS)
    if collision:
        raise SchemaCompatibilityError(
            f"Source contains reserved lineage columns: {sorted(collision)}"
        )
    return (
        data.withColumn("_ingestion_id", F.lit(ingestion_id))
        .withColumn("_ingestion_timestamp", F.current_timestamp())
        .withColumn("_ingestion_date", F.current_date())
        .withColumn("_source_name", F.lit(source_name))
        .withColumn("_source_file", F.lit(source_file))
        .withColumn("_source_file_hash", F.lit(source_file_hash))
    )


def append_iceberg(
    spark: SparkSession, data: DataFrame, table: str, schema_behavior: str = "additive"
) -> None:
    """Append to an Iceberg table; optionally accept additive schema evolution."""
    if len(data.columns) != len(set(data.columns)):
        raise SchemaCompatibilityError("Source schema contains duplicate column names")
    namespace = ".".join(table.split(".")[:2])
    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {namespace}")
    if not spark.catalog.tableExists(table):
        writer = (
            data.writeTo(table)
            .using("iceberg")
            .partitionedBy(F.col("_ingestion_date"))
            .tableProperty("sod.partitioning", "_ingestion_date")
        )
        if schema_behavior == "additive":
            writer = writer.tableProperty("write.spark.accept-any-schema", "true")
        writer.create()
        return

    current = spark.table(table).schema
    incoming = data.schema
    current_fields = {field.name: field.dataType for field in current.fields}
    incoming_fields = {field.name: field.dataType for field in incoming.fields}
    if schema_behavior == "strict":
        if current_fields != incoming_fields:
            raise SchemaCompatibilityError(
                f"Strict schema mismatch for {table}: current={current_fields}, incoming={incoming_fields}"
            )
        _ensure_ingestion_date_partition(spark, table)
        data.writeTo(table).append()
        return

    safe_promotions = {(IntegerType(), LongType()), (FloatType(), DoubleType())}
    incompatible = {
        name: (current_fields[name], incoming_fields[name])
        for name in current_fields.keys() & incoming_fields.keys()
        if current_fields[name] != incoming_fields[name]
        and (current_fields[name], incoming_fields[name]) not in safe_promotions
    }
    if incompatible:
        raise SchemaCompatibilityError(
            f"Incompatible schema changes for {table}: {incompatible}"
        )
    for name in current_fields.keys() - incoming_fields.keys():
        data = data.withColumn(name, F.lit(None).cast(current_fields[name]))
    # Iceberg's Spark writer checks the incoming field order during schema evolution.
    # Keep existing columns in table order and append newly discovered columns.
    ordered_columns = [name for name in current_fields if name in data.columns] + [
        name for name in data.columns if name not in current_fields
    ]
    data = data.select(*ordered_columns)
    _ensure_ingestion_date_partition(spark, table)
    spark.sql(
        f"ALTER TABLE {table} SET TBLPROPERTIES "
        "('write.spark.accept-any-schema'='true')"
    )
    data.writeTo(table).option("mergeSchema", "true").append()


def _ensure_ingestion_date_partition(spark: SparkSession, table: str) -> None:
    """Evolve existing Iceberg tables to partition future writes by ingestion date."""
    columns = set(spark.table(table).columns)
    if "_ingestion_date" not in columns:
        spark.sql(f"ALTER TABLE {table} ADD COLUMN _ingestion_date DATE")
    properties = {
        row[0]: row[1] for row in spark.sql(f"SHOW TBLPROPERTIES {table}").collect()
    }
    if properties.get("sod.partitioning") == "_ingestion_date":
        return
    spark.sql(f"ALTER TABLE {table} ADD PARTITION FIELD _ingestion_date")
    spark.sql(
        f"ALTER TABLE {table} SET TBLPROPERTIES ('sod.partitioning'='_ingestion_date')"
    )
