"""CLI for persisted Access Intelligence materializations and diagnostics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sod_platform.access_intelligence.pipeline import OUTPUTS, run_access_intelligence
from sod_platform.bronze.ingestion.spark import create_spark_session
from sod_platform.common.env import load_project_env
from sod_platform.observability.logging import configure_logging


def main() -> int:
    parser = argparse.ArgumentParser(description="Run and inspect persisted Access Intelligence outputs")
    parser.add_argument("command", choices=("run", "status", "metrics", "inspect"))
    parser.add_argument("--config", type=Path, default=Path("configs/access_intelligence.yml"))
    parser.add_argument("--component", choices=tuple(OUTPUTS))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--log-file", type=Path, default=Path("logs/access_intelligence/processing.log"))
    args = parser.parse_args()
    root = Path.cwd()
    load_project_env(root)
    configure_logging(args.log_file)
    spark = create_spark_session(root, "sod-platform-access-intelligence")
    try:
        if args.command == "run":
            print(json.dumps(run_access_intelligence(spark, root / args.config), default=str, sort_keys=True))
            return 0
        if args.command in ("status", "metrics"):
            table = "sod.metadata.access_intelligence_runs"
            if not spark.catalog.tableExists(table):
                print("No Access Intelligence execution has been persisted.")
                return 0
            query = spark.table(table).orderBy("finished_at", ascending=False)
            if args.component:
                query = query.where(f"component = '{args.component}'")
            query.limit(args.limit).show(truncate=False)
            return 0
        if not args.component:
            parser.error("inspect requires --component")
        table = OUTPUTS[args.component]
        if not spark.catalog.tableExists(table):
            print(f"No persisted output for {args.component}.")
            return 0
        spark.table(table).limit(args.limit).show(truncate=False)
        return 0
    finally:
        spark.stop()


if __name__ == "__main__":
    raise SystemExit(main())
