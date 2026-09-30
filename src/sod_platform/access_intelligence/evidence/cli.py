"""CLI for EV001 materialization and inspection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sod_platform.bronze.ingestion.spark import create_spark_session
from sod_platform.common.env import load_project_env
from sod_platform.observability.logging import configure_logging

from .pipeline import OUTPUTS, run_evidence_engine


def main() -> int:
    parser = argparse.ArgumentParser(description="Run and inspect the Evidence Engine")
    parser.add_argument("command", choices=("run", "status", "metrics", "inspect"))
    parser.add_argument(
        "--config", type=Path, default=Path("configs/evidence_engine.yml")
    )
    parser.add_argument("--output", choices=tuple(OUTPUTS))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--log-file", type=Path, default=Path("logs/evidence/processing.log")
    )
    args = parser.parse_args()
    root = Path.cwd()
    load_project_env(root)
    configure_logging(args.log_file)
    spark = create_spark_session(root, "sod-platform-evidence-engine")
    try:
        if args.command == "run":
            config = args.config if args.config.is_absolute() else root / args.config
            print(
                json.dumps(
                    run_evidence_engine(spark, config), default=str, sort_keys=True
                )
            )
            return 0
        if args.command in ("status", "metrics"):
            table = "sod.metadata.access_intelligence_runs"
            if not spark.catalog.tableExists(table):
                print("No Evidence Engine execution has been persisted.")
                return 0
            spark.table(table).where("component = 'evidence_engine'").orderBy(
                "finished_at", ascending=False
            ).limit(args.limit).show(truncate=False)
            return 0
        if not args.output:
            parser.error("inspect requires --output")
        table = OUTPUTS[args.output]
        if not spark.catalog.tableExists(table):
            print(f"No persisted output for {args.output}.")
            return 0
        spark.table(table).limit(args.limit).show(truncate=False)
        return 0
    finally:
        spark.stop()


if __name__ == "__main__":
    raise SystemExit(main())
