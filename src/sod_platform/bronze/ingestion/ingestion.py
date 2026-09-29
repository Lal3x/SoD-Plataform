"""Read source/schema groups and commit file lineage atomically to Iceberg."""

from __future__ import annotations

import json

from pyspark import StorageLevel
from pyspark.sql import functions as F

from sod_platform.bronze.ingestion.readers import SourceReadError, read_source
from sod_platform.bronze.writer import (
    LINEAGE_COLUMNS,
    SchemaCompatibilityError,
    append_iceberg,
)


def ingest_group(spark, source, runs, schema):
    """Read identical schemas together, aggregate once, then commit atomically.

    Split only read failures. Never retry a failed/ambiguous write in this invocation.
    """
    from functools import reduce
    from urllib.parse import unquote, urlsplit

    from sod_platform.bronze.ingestion.discovery import sha256_file

    def canonical(path):
        parsed = urlsplit(path)
        return (parsed.scheme.replace("s3a", "s3"), parsed.netloc, unquote(parsed.path))

    data = None
    try:
        paths = [r["source_file"].replace("s3://", "s3a://", 1) for r in runs]
        if source.format == "xlsx":
            data = reduce(
                lambda a, b: a.unionByName(b),
                [
                    read_source(
                        spark, r["source_file"], source.format, source.options
                    ).withColumn("_source_file", F.lit(r["source_file"]))
                    for r in runs
                ],
            )
        else:
            data = (
                spark.read.options(**source.options)
                .option("mode", "FAILFAST")
                .schema(schema)
                .format(source.format)
                .load(paths)
                .withColumn("_source_file", F.input_file_name())
            )
        data = data.persist(StorageLevel.MEMORY_AND_DISK)
        aggregates = [F.count("*").alias("received")]
        if "batch_id" in data.columns:
            aggregates.append(F.collect_set("batch_id").alias("batches"))
        if "extract_timestamp" in data.columns:
            aggregates.append(
                F.avg(
                    F.unix_timestamp(F.current_timestamp())
                    - F.unix_timestamp(
                        F.expr("try_cast(extract_timestamp as timestamp)")
                    )
                ).alias("latency")
            )
        statistics = data.groupBy("_source_file").agg(*aggregates).collect()
        by_path = {canonical(r["source_file"]): r for r in runs}
        actual_paths = {}
        for stat in statistics:
            run = by_path[canonical(stat["_source_file"])]
            actual_paths[run["source_file"]] = stat["_source_file"]
            run["records_received"] = stat["received"]
            if "batches" in stat.asDict():
                run["source_batches"] = json.dumps(stat["batches"], default=str)
            if "latency" in stat.asDict():
                run["latency_seconds"] = stat["latency"]
        for run in runs:
            if sha256_file(run["source_file"]) != run["source_file_hash"]:
                raise SourceReadError("Source changed during read")
    except Exception as exc:  # noqa: BLE001 - isolate reads before any commit
        if data is not None:
            data.unpersist()
        if len(runs) > 1:
            middle = len(runs) // 2
            ingest_group(spark, source, runs[:middle], schema)
            ingest_group(spark, source, runs[middle:], schema)
        else:
            fail_run(runs[0], exc, "read")
        return

    try:
        current = {}
        if spark.catalog.tableExists(source.target_table):
            current = {
                f.name: f.dataType.simpleString()
                for f in spark.table(source.target_table).schema
                if f.name not in LINEAGE_COLUMNS
            }
        incoming = {f.name: f.dataType.simpleString() for f in schema}
        event = json.dumps(
            {
                "new": sorted(incoming.keys() - current.keys()),
                "missing": sorted(current.keys() - incoming.keys()),
                "changed": {
                    k: [current[k], incoming[k]]
                    for k in current.keys() & incoming.keys()
                    if current[k] != incoming[k]
                },
            }
        )
        for run in runs:
            run["schema_event"] = event
        lookup = spark.createDataFrame(
            [
                (
                    actual_paths.get(r["source_file"], r["source_file"]),
                    r["source_file"],
                    r["source_file_hash"],
                    r["ingestion_id"],
                )
                for r in runs
            ],
            "__input_file string, _source_file string, _source_file_hash string, _ingestion_id string",
        )
        enriched = (
            data.alias("raw")
            .join(
                F.broadcast(lookup).alias("lineage"),
                F.col("raw._source_file") == F.col("lineage.__input_file"),
                "inner",
            )
            .select(
                *[
                    F.col("raw.`" + name.replace("`", "``") + "`")
                    for name in schema.fieldNames()
                ],
                F.col("lineage._source_file"),
                F.col("lineage._source_file_hash"),
                F.col("lineage._ingestion_id"),
            )
            .withColumn("_source_name", F.lit(source.source_name))
            .withColumn("_ingestion_timestamp", F.current_timestamp())
            .withColumn("_ingestion_date", F.current_date())
        )
        append_iceberg(spark, enriched, source.target_table, source.schema_behavior)
        for run in runs:
            run.update(status="SUCCEEDED", records_written=run["records_received"])
    except Exception as exc:  # noqa: BLE001 - writes must never be retried blindly
        for run in runs:
            fail_run(
                run,
                exc,
                (
                    "schema"
                    if isinstance(exc, SchemaCompatibilityError)
                    else "infrastructure"
                ),
            )
    finally:
        data.unpersist()


def fail_run(run, exc, category):
    """Keep raw exception text (which may contain personal data) out of audit/logs."""
    run.update(
        status="FAILED",
        error_category=category,
        error_type=type(exc).__name__,
        error_message=f"{category} operation failed; inspect schema_event and source reference",
    )
