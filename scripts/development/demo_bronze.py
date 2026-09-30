"""Demonstrate two arrivals and replay using real inputs in an isolated warehouse."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from sod_platform.bronze.ingestion.config import load_sources
from sod_platform.bronze.ingestion.spark import create_spark_session
from sod_platform.bronze.pipeline import run_bronze


def main():
    root = Path(__file__).resolve().parents[2]
    workspace = Path(tempfile.mkdtemp(prefix="sod-bronze-demo-"))
    os.environ["SOD_WAREHOUSE"] = str(workspace / "warehouse")
    os.environ.setdefault("SPARK_MASTER", "local[2]")
    sources = load_sources(root / "configs/sources.yml")
    selected = {}
    for source in sources:
        files = sorted(root.glob(source.path))[:2]
        if len(files) != 2:
            raise ValueError(f"Demo needs two files for {source.source_name}")
        selected[source.source_name] = files
        target = workspace / files[0].relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(files[0], target)
    spark = create_spark_session(root, "sod-bronze-demo")
    try:
        report = {"warehouse": str(workspace / "warehouse")}
        report["first"] = run_bronze(spark, sources, workspace)
        for files in selected.values():
            shutil.copy2(files[1], workspace / files[1].relative_to(root))
        report["incremental"] = run_bronze(spark, sources, workspace)
        report["replay"] = run_bronze(spark, sources, workspace)
        report["tables"] = {
            source.target_table: spark.table(source.target_table).count()
            for source in sources
        }
        report["audit"] = [
            r.asDict()
            for r in spark.sql(
                "SELECT source_name, status, count(*) AS events, sum(records_written) AS rows_written FROM sod.metadata.ingestion_runs GROUP BY source_name, status ORDER BY source_name, status"
            ).collect()
        ]
        report["execution_events"] = spark.table(
            "sod.metadata.bronze_executions"
        ).count()
        assert report["first"]["files_processed"] == 7
        assert report["incremental"]["files_processed"] == 7
        assert report["incremental"]["files_skipped"] == 7
        assert report["replay"]["files_skipped"] == 14
        assert all(
            report[phase]["files_failed"] == 0
            for phase in ("first", "incremental", "replay")
        )
        destination = root / "artifacts/validation/bronze-demo-results.json"
        destination.write_text(json.dumps(report, indent=2))
        print(f"Report: {destination}; warehouse: {workspace / 'warehouse'}")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
