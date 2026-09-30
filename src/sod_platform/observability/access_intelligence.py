"""Persistent operational journal for the materialized Access Intelligence stages.

This extends the existing Iceberg observability convention.  A run is keyed by
the already-published ``_silver_run_id`` that supplied Access Context; it does
not introduce a competing pipeline run identifier.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

TABLE = "sod.metadata.access_intelligence_runs"
SCHEMA = (
    "run_id string, component string, status string, started_at timestamp, "
    "finished_at timestamp, duration_seconds double, metrics_json string"
)


def append_component_run(
    spark: SparkSession,
    *,
    run_id: str,
    component: str,
    status: str,
    started_at: datetime,
    duration_seconds: float,
    metrics: dict,
) -> None:
    """Append a terminal component event to the platform's metadata journal."""
    finished_at = datetime.now(UTC).replace(tzinfo=None)
    frame = spark.createDataFrame(
        [
            (
                run_id,
                component,
                status,
                started_at.replace(tzinfo=None),
                finished_at,
                duration_seconds,
                json.dumps(metrics, sort_keys=True),
            )
        ],
        SCHEMA,
    )
    spark.sql("CREATE NAMESPACE IF NOT EXISTS sod.metadata")
    if spark.catalog.tableExists(TABLE):
        frame.writeTo(TABLE).append()
    else:
        frame.writeTo(TABLE).using("iceberg").create()


def distribution(frame: DataFrame, column: str) -> dict[str, int]:
    """Return an explicit distribution, retaining null as UNKNOWN."""
    return {
        str(row["value"] if row["value"] is not None else "UNKNOWN"): row["count"]
        for row in frame.groupBy(F.col(column).alias("value")).count().collect()
    }
