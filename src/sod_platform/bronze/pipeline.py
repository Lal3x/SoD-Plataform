"""Configuration-driven, idempotent Bronze file ingestion."""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any

from pyspark.sql import SparkSession

from sod_platform.bronze.ingestion.config import SourceConfig
from sod_platform.bronze.ingestion.discovery import discover_files, sha256_file
from sod_platform.bronze.ingestion.ingestion import fail_run, ingest_group
from sod_platform.bronze.ingestion.metadata import (
    RUN_SCHEMA,
    RUN_TABLE,
    ensure_namespace,
    utc_now,
    write_runs,
)
from sod_platform.bronze.ingestion.readers import read_source
from sod_platform.bronze.writer import LINEAGE_COLUMNS, SchemaCompatibilityError
from sod_platform.observability.metrics import BatchMetrics

logger = logging.getLogger(__name__)


def _successful_run_hashes(spark: SparkSession, table: str) -> set[str]:
    hashes = set()
    if spark.catalog.tableExists(table) and spark.catalog.tableExists(RUN_TABLE):
        hashes.update(
            row[0]
            for row in spark.table(RUN_TABLE)
            .where(f"target_table = '{table}' AND status IN ('SUCCEEDED', 'success')")
            .select("source_file_hash")
            .distinct()
            .collect()
            if row[0] is not None
        )
    if spark.catalog.tableExists(table):
        hashes.update(
            r[0]
            for r in spark.table(table).select("_source_file_hash").distinct().collect()
        )
    return hashes


def _ensure_run_table(spark: SparkSession) -> None:
    ensure_namespace(spark, "sod.metadata")
    if not spark.catalog.tableExists(RUN_TABLE):
        spark.createDataFrame([], RUN_SCHEMA).writeTo(RUN_TABLE).using(
            "iceberg"
        ).create()
        return

    existing_columns = set(spark.table(RUN_TABLE).columns)
    sql_types = {
        "string": "STRING",
        "double": "DOUBLE",
        "bigint": "BIGINT",
        "timestamp": "TIMESTAMP",
    }
    missing_columns = [
        f"{field.name} {sql_types[field.dataType.simpleString()]}"
        for field in RUN_SCHEMA.fields
        if field.name not in existing_columns
    ]
    if missing_columns:
        spark.sql(f"ALTER TABLE {RUN_TABLE} ADD COLUMNS ({', '.join(missing_columns)})")


def run_bronze(
    spark: SparkSession, sources: list[SourceConfig], base_dir: Path
) -> dict[str, Any]:
    """Process source/schema groups; Iceberg commits precede successful audit events.

    A single writer per target table is required by this local Hadoop catalog.
    Audit tables are append-only STARTED/terminal event journals.
    """
    import json
    from datetime import datetime

    import fsspec

    from sod_platform.bronze.ingestion.metadata import write_execution

    started = time.monotonic()
    batch_id = str(uuid.uuid4())
    metrics = BatchMetrics(batch_id=batch_id)
    _ensure_run_table(spark)
    execution_started = utc_now()
    per_source = {}

    def execution(source_name, status, started_at, summary):
        write_execution(
            spark,
            {
                "batch_id": batch_id,
                "source_name": source_name,
                "status": status,
                "started_at": started_at,
                "finished_at": None if status == "STARTED" else utc_now(),
                "metrics_json": json.dumps(summary),
            },
        )

    def log(event, **fields):
        logger.info(json.dumps(dict(event=event, batch_id=batch_id, **fields)))

    execution("*", "STARTED", execution_started, metrics.as_dict())
    for source in sources:
        source_started = utc_now()
        timer = time.monotonic()
        counts = BatchMetrics(batch_id=batch_id)
        execution(source.source_name, "STARTED", source_started, counts.as_dict())
        try:
            files = discover_files(source.path, base_dir)
            # Validation fixtures can never be an ingestion source, even through broad globs.
            if any(
                Path(p).name == "gabarito.csv" or "/tests/fixtures/" in p for p in files
            ):
                raise ValueError("Validation fixtures are not sources")
            known_hashes = _successful_run_hashes(spark, source.target_table)
        except Exception as exc:  # noqa: BLE001 - isolate source/file failures
            counts.files_failed += 1
            log(
                "source_discovery_failed",
                source=source.source_name,
                error_type=type(exc).__name__,
            )
            files = []
        counts.files_discovered = len(files)
        runs = []
        for path in files:
            run = {field.name: None for field in RUN_SCHEMA}
            run.update(
                batch_id=batch_id,
                ingestion_id=str(uuid.uuid4()),
                source_name=source.source_name,
                target_table=source.target_table,
                source_file=path,
                started_at=utc_now(),
                status="STARTED",
                records_received=0,
                records_written=0,
            )
            runs.append(run)
        # One STARTED commit per source, before reading input bytes.
        write_runs(spark, runs)
        groups = {}
        duplicates = []
        pending = {}
        for run in runs:
            path = run["source_file"]
            try:
                fs, inner = fsspec.core.url_to_fs(path)
                run["file_bytes"] = fs.size(inner)
                digest = sha256_file(path)
                run["source_file_hash"] = digest
                parts = Path(inner).stem.split("__")
                if len(parts) == 4:
                    run.update(
                        source_batches=json.dumps([parts[3]]),
                        filename_source_system=parts[0],
                        filename_source_name=parts[1],
                        filename_extract_timestamp=parts[2],
                    )
                    try:
                        run["latency_seconds"] = (
                            run["started_at"] - datetime.fromisoformat(parts[2])
                        ).total_seconds()
                    except (ValueError, TypeError):
                        pass
                if digest in known_hashes:
                    run["status"] = "SKIPPED"
                    continue
                if digest in pending:
                    duplicates.append((run, pending[digest]))
                    continue
                schema = read_source(spark, path, source.format, source.options).schema
                names = schema.fieldNames()
                missing = set(source.required_columns) - set(names)
                reserved = set(names) & set(LINEAGE_COLUMNS)
                if missing or reserved:
                    run["schema_event"] = json.dumps(
                        {
                            "missing_required": sorted(missing),
                            "reserved": sorted(reserved),
                        }
                    )
                    raise SchemaCompatibilityError("Invalid structural columns")
                key = schema.json()
                groups.setdefault(key, (schema, []))[1].append(run)
                pending[digest] = run
            except Exception as exc:  # noqa: BLE001 - isolate each input
                fail_run(
                    run,
                    exc,
                    "schema" if isinstance(exc, SchemaCompatibilityError) else "read",
                )
        for schema, group in groups.values():
            group_started = time.monotonic()
            log("group_started", source=source.source_name, file_count=len(group))
            ingest_group(spark, source, group, schema)
            log(
                "group_finished",
                source=source.source_name,
                file_count=len(group),
                duration_seconds=round(time.monotonic() - group_started, 3),
            )
        for run, original in duplicates:
            if original["status"] == "SUCCEEDED":
                run["status"] = "SKIPPED"
            else:
                fail_run(
                    run,
                    RuntimeError("Duplicate of failed input"),
                    original["error_category"],
                )
        for run in runs:
            run.update(
                finished_at=utc_now(),
                duration_seconds=(utc_now() - run["started_at"]).total_seconds(),
            )
            counts.bytes_discovered += run["file_bytes"] or 0
            counts.records_received += run["records_received"]
            counts.records_written += run["records_written"]
            if run["status"] == "SUCCEEDED":
                counts.files_processed += 1
                counts.bytes_processed += run["file_bytes"] or 0
            elif run["status"] == "SKIPPED":
                counts.files_skipped += 1
            else:
                counts.files_failed += 1
            log(
                "file_finished",
                _ingestion_id=run["ingestion_id"],
                source=source.source_name,
                file=run["source_file"],
                status=run["status"],
                records_read=run["records_received"],
                records_written=run["records_written"],
                error_category=run["error_category"],
            )
        write_runs(
            spark,
            [r for r in runs if r["status"] == "FAILED"],
            "sod.metadata.bronze_quarantine",
        )
        # Failure here propagates; replay consults Bronze hashes to recover committed groups.
        write_runs(spark, runs)
        counts.duration_seconds = round(time.monotonic() - timer, 3)
        per_source[source.source_name] = counts.as_dict()
        execution(
            source.source_name,
            "FAILED" if counts.files_failed else "SUCCEEDED",
            source_started,
            counts.as_dict(),
        )
        for name in (
            "files_discovered",
            "files_processed",
            "files_skipped",
            "files_failed",
            "records_received",
            "records_written",
            "bytes_discovered",
            "bytes_processed",
        ):
            setattr(metrics, name, getattr(metrics, name) + getattr(counts, name))
    metrics.duration_seconds = round(time.monotonic() - started, 3)
    result = dict(metrics.as_dict(), sources=per_source)
    execution(
        "*",
        "FAILED" if metrics.files_failed else "SUCCEEDED",
        execution_started,
        result,
    )
    log("batch_finished", metrics=result)
    return result
