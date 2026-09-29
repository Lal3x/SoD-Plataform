"""Build conforming Silver Iceberg snapshots and auditable access context."""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import yaml
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from sod_platform.access_intelligence.context.engine import GRANT, build_access_context

from .contract import TABLE_ALIASES, canonicalize_raw_tables
from .preparation import prepare_silver
from .quality.validation import validate_with_gx

logger = logging.getLogger(__name__)
RUN_SCHEMA = "silver_run_id string, started_at timestamp, finished_at timestamp, duration_seconds double, status string, records_in bigint, records_written bigint, records_quarantined bigint, counts_by_table string"


def _write_snapshot(df: DataFrame, table: str) -> None:
    spark = df.sparkSession
    namespace = ".".join(table.split(".")[:-1])
    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {namespace}")
    if spark.catalog.tableExists(table):
        # Explicit additive evolution for Silver metadata; never drop existing fields.
        current = spark.table(table).schema
        missing = [
            f"`{f.name}` {f.dataType.simpleString()}"
            for f in df.schema
            if f.name not in current.names
        ]
        if missing:
            spark.sql(f"ALTER TABLE {table} ADD COLUMNS ({', '.join(missing)})")
        for field in current:
            if field.name not in df.columns:
                df = df.withColumn(field.name, F.lit(None).cast(field.dataType))
        df.select(*spark.table(table).columns).writeTo(table).overwrite(F.lit(True))
    else:
        df.writeTo(table).using("iceberg").create()


def _append(df: DataFrame, table: str) -> None:
    df.sparkSession.sql(
        f"CREATE NAMESPACE IF NOT EXISTS {'.'.join(table.split('.')[:-1])}"
    )
    if df.sparkSession.catalog.tableExists(table):
        df.writeTo(table).append()
    else:
        df.writeTo(table).using("iceberg").create()


def run_silver(
    spark: SparkSession,
    config_path: Path,
    reference_date: date | None = None,
    *,
    include_access_context: bool = True,
) -> dict:
    """Overwrite current snapshots; append run history. Consumers require a successful run.

    Iceberg commits are atomic per table, not across the published tables. Failure is audited
    and re-raised; rerun repairs partial publication. Never consume a failed run.
    """
    run_id = str(uuid.uuid4())
    started = time.monotonic()
    now = datetime.now(UTC).replace(tzinfo=None)
    reference_date = reference_date or now.date()
    cached = []
    counts, input_counts, metrics = {}, {}, {}
    quarantine_count = 0
    persisted_counts = {}
    write_seconds = {}
    phase_seconds = {}
    phase, phase_started = "read", time.monotonic()

    def next_phase(name):
        nonlocal phase, phase_started
        phase_seconds[phase] = round(time.monotonic() - phase_started, 3)
        phase, phase_started = name, time.monotonic()

    status = "failed"
    logger.info(
        "silver_run_started run_id=%s reference_date=%s", run_id, reference_date
    )
    try:
        _append(
            spark.createDataFrame(
                [
                    (
                        run_id,
                        now,
                        None,
                        0.0,
                        "started",
                        0,
                        0,
                        0,
                        json.dumps({"reference_date": reference_date.isoformat()}),
                    )
                ],
                RUN_SCHEMA,
            ),
            "sod.metadata.silver_runs",
        )
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        raw = {}
        for name, table in config["tables"].items():
            raw[name] = spark.table(table).cache()
            cached.append(raw[name])
            input_counts[name] = raw[name].count()
        next_phase("prepare_and_quality")
        valid, rejects, transformed = prepare_silver(raw, config, run_id, cached=cached)
        valid = canonicalize_raw_tables(valid)
        transformed = canonicalize_raw_tables(transformed)
        input_counts = {TABLE_ALIASES.get(k, k): v for k, v in input_counts.items()}
        source_tables = {
            TABLE_ALIASES.get(k, k): v for k, v in config["tables"].items()
        }
        for name, frame in valid.items():
            valid[name] = frame.cache()
            cached.append(valid[name])
            counts[name] = valid[name].count()
        quarantine_df = rejects[0]
        for frame in rejects[1:]:
            quarantine_df = quarantine_df.unionByName(frame)
        quarantine_df = quarantine_df.withColumn("detected_at", F.lit(now)).cache()
        cached.append(quarantine_df)
        quarantine_count = quarantine_df.count()
        if sum(input_counts.values()) != sum(counts.values()) + quarantine_count:
            raise ValueError(
                "Silver accounting mismatch: every input needs a disposition"
            )
        context = None
        context_count = 0
        if include_access_context:
            next_phase("access_context")
            context = build_access_context(valid, reference_date).cache()
            cached.append(context)
            context_count = context.count()
            if context.select(*GRANT).distinct().count() != context_count:
                raise ValueError(
                    "Access context violated one-row-per-active-grant contract"
                )

        next_phase("diagnostics")
        quality_rows = []
        for name, frame in transformed.items():
            for check in validate_with_gx(name, frame, config.get("domains", {})):
                quality_rows.append(
                    (
                        run_id,
                        source_tables[name],
                        check["expectation_type"],
                        check["column"],
                        check["success"],
                        check["result"],
                        now,
                    )
                )
        reason_counts = {
            r.error_code: r["count"]
            for r in quarantine_df.groupBy("error_code").count().collect()
        }
        requests = valid["iga_access_requests"]
        unmatched = (
            requests.where(F.col("grant_id").isNotNull())
            .join(
                valid["iga_access_assignments"].select("grant_id"),
                "grant_id",
                "left_anti",
            )
            .count()
            if "grant_id" in requests.columns
            else 0
        )
        generated_grant_ids = (
            context.where("grant_id_generated").count()
            if context is not None and "grant_id_generated" in context.columns
            else None
        )
        metrics = {
            "reference_date": reference_date.isoformat(),
            "input_records": sum(input_counts.values()),
            "valid_records": sum(counts.values()),
            "silver_records": sum(counts.values()),
            "quarantined_records": quarantine_count,
            "duplicate_records": sum(
                v for k, v in reason_counts.items() if k.startswith("DUPLICATE")
            ),
            "invalid_fk_records": sum(
                v for k, v in reason_counts.items() if k.endswith("REFERENCE")
            ),
            "dq_failures": sum(not row[4] for row in quality_rows),
            "access_context_records": context_count if include_access_context else None,
            "unmatched_approval_records": unmatched,
            "access_context_metrics": (
                {
                    "active_grants": context_count,
                    "distinct_grant_ids": (
                        context.select("grant_id").distinct().count()
                        if context is not None
                        else None
                    ),
                    "generated_grant_ids": generated_grant_ids,
                    "approval_relevance": {
                        str(row["approval_relevance"]): row["count"]
                        for row in context.groupBy("approval_relevance")
                        .count()
                        .collect()
                    },
                    "usage_coverage": {
                        str(row["usage_coverage"]): row["count"]
                        for row in context.groupBy("usage_coverage").count().collect()
                    },
                    "identity_history_complete": {
                        str(row["identity_history_complete"]): row["count"]
                        for row in context.groupBy("identity_history_complete")
                        .count()
                        .collect()
                    },
                    "cross_community": {
                        str(row["cross_community"]): row["count"]
                        for row in context.groupBy("cross_community").count().collect()
                    },
                    "grain_integrity": "VALIDATED",
                    "join_explosion_detected": False,
                }
                if context is not None
                else None
            ),
            "quarantine_by_reason": reason_counts,
            "tables": {
                name: {
                    "input_records": input_counts[name],
                    "valid_records": counts[name],
                    "quarantined_records": input_counts[name] - counts[name],
                }
                for name in counts
            },
        }
        context_metrics = metrics["access_context_metrics"]
        if context_metrics is not None:
            context_metrics["generated_grant_id_rate"] = (
                round(generated_grant_ids / context_count, 6)
                if generated_grant_ids is not None and context_count
                else None
            )
        # Materialize and validate everything before publishing any output.
        next_phase("publish")
        outputs = {**valid}
        if context is not None:
            outputs["access_context"] = context
        for name, frame in outputs.items():
            output = frame.withColumn("_silver_processed_at", F.lit(now)).withColumn(
                "_silver_run_id", F.lit(run_id)
            )
            write_started = time.monotonic()
            _write_snapshot(output, f"sod.silver.{name}")
            write_seconds[name] = round(time.monotonic() - write_started, 3)
            persisted_counts[name] = (
                context_count if name == "access_context" else counts[name]
            )
        _write_snapshot(quarantine_df, "sod.quality.quarantine")
        quality_schema = "_silver_run_id string, source_table string, expectation_type string, column string, success boolean, result string, evaluated_at timestamp"
        _append(
            spark.createDataFrame(quality_rows, quality_schema),
            "sod.quality.data_quality_results",
        )
        status = "success"
    except Exception as exc:
        metrics["error"] = type(exc).__name__
        metrics["failed_phase"] = phase
        logger.exception(
            "silver_run_failed run_id=%s error_type=%s", run_id, type(exc).__name__
        )
        raise
    finally:
        next_phase("audit")
        duration = round(time.monotonic() - started, 3)
        metrics.update(
            processing_time=duration,
            run_status=status,
            persisted_counts=persisted_counts,
            phase_seconds=phase_seconds,
            write_seconds_by_table=write_seconds,
            input_rows_per_second=round(
                sum(input_counts.values()) / max(duration, 0.001), 2
            ),
        )
        try:
            audit = spark.createDataFrame(
                [
                    (
                        run_id,
                        now,
                        datetime.now(UTC).replace(tzinfo=None),
                        duration,
                        status,
                        sum(input_counts.values()),
                        sum(persisted_counts.values()),
                        quarantine_count,
                        json.dumps(metrics, sort_keys=True),
                    )
                ],
                RUN_SCHEMA,
            )
            _append(audit, "sod.metadata.silver_runs")
        except Exception:
            logger.exception("silver_audit_failed run_id=%s", run_id)
            if status == "success":
                raise
        finally:
            for frame in cached:
                frame.unpersist()
    result = {
        "silver_run_id": run_id,
        "rows_written": counts,
        "quarantined": quarantine_count,
        "quality_checks": len(quality_rows),
        "duration_seconds": duration,
        **metrics,
    }
    logger.info("silver_run_finished metrics=%s", result)
    return result
