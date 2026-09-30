"""Measure a full arrival and replay without changing the configured warehouse."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from sod_platform.bronze.ingestion.config import load_sources
from sod_platform.bronze.ingestion.spark import create_spark_session
from sod_platform.bronze.pipeline import run_bronze


def main():
    root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="sod-bronze-benchmark-") as temporary:
        os.environ["SOD_WAREHOUSE"] = str(Path(temporary) / "warehouse")
        os.environ.setdefault("SPARK_MASTER", "local[2]")
        sources = load_sources(root / "configs/sources.yml")
        spark = create_spark_session(root, "sod-bronze-benchmark")
        try:
            report = {
                "spark_master": spark.sparkContext.master,
                "initial": run_bronze(spark, sources, root),
                "replay": run_bronze(spark, sources, root),
            }
            report["tables"] = {
                s.target_table: {
                    "rows": spark.table(s.target_table).count(),
                    "snapshots": spark.table(s.target_table + ".snapshots").count(),
                }
                for s in sources
            }
            assert report["initial"]["files_failed"] == 0
            assert report["replay"]["files_failed"] == 0
            assert report["replay"]["records_written"] == 0
            assert (
                report["replay"]["files_skipped"]
                == report["initial"]["files_discovered"]
            )
            assert (
                sum(t["rows"] for t in report["tables"].values())
                == report["initial"]["records_written"]
            )
            output = root / "artifacts/validation/bronze-benchmark.json"
            output.write_text(json.dumps(report, indent=2))
            print(f"Report: {output}")
            print(
                json.dumps(
                    {k: report[k]["duration_seconds"] for k in ("initial", "replay")}
                )
            )
        finally:
            spark.stop()


if __name__ == "__main__":
    main()
