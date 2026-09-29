"""CLI for PD001 materialization and inspection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sod_platform.bronze.ingestion.spark import create_spark_session
from sod_platform.common.env import load_project_env
from sod_platform.observability.logging import configure_logging

from .pipeline import OUTPUTS, run_policy_decision


def main() -> int:
    parser = argparse.ArgumentParser(description="Run and inspect Policy Decision PD001")
    parser.add_argument("command", choices=("run", "status", "metrics", "inspect"))
    parser.add_argument("--config", type=Path, default=Path("configs/policy_decision.yml"))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--log-file", type=Path, default=Path("logs/policy/processing.log"))
    args = parser.parse_args()
    root = Path.cwd()
    load_project_env(root)
    configure_logging(args.log_file)
    spark = create_spark_session(root, "sod-platform-policy-decision")
    try:
        if args.command == "run":
            config = args.config if args.config.is_absolute() else root / args.config
            print(json.dumps(run_policy_decision(spark, config), default=str, sort_keys=True))
            return 0
        if args.command in ("status", "metrics"):
            table = "sod.metadata.access_intelligence_runs"
            if not spark.catalog.tableExists(table):
                print("No Policy Decision execution has been persisted.")
                return 0
            spark.table(table).where("component = 'policy_decision'").orderBy("finished_at", ascending=False).limit(args.limit).show(truncate=False)
            return 0
        table = OUTPUTS["policy_decisions"]
        if not spark.catalog.tableExists(table):
            print("No persisted output for policy_decisions.")
            return 0
        spark.table(table).limit(args.limit).show(truncate=False)
        return 0
    finally:
        spark.stop()


if __name__ == "__main__":
    raise SystemExit(main())
