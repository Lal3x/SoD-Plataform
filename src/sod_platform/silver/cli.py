"""CLI for building Silver Iceberg snapshots."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from sod_platform.bronze.ingestion.spark import create_spark_session
from sod_platform.common.env import load_project_env
from sod_platform.observability.logging import configure_logging
from sod_platform.silver.pipeline import run_silver


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build Silver tables from Iceberg Bronze"
    )
    parser.add_argument("--config", type=Path, default=Path("configs/data_quality.yml"))
    parser.add_argument(
        "--log-file", type=Path, default=Path("logs/silver/processing.log")
    )
    parser.add_argument(
        "--reference-date",
        type=date.fromisoformat,
        help="Data de referência YYYY-MM-DD (padrão: hoje UTC)",
    )
    parser.add_argument(
        "--silver-only",
        action="store_true",
        help="Materialize only normalized Silver, quality, quarantine and audit tables",
    )
    args = parser.parse_args()
    configure_logging(args.log_file)
    root = Path.cwd()
    load_project_env(root)
    spark = create_spark_session(root, "sod-platform-silver")
    try:
        print(
            run_silver(
                spark,
                args.config if args.config.is_absolute() else root / args.config,
                args.reference_date,
                include_access_context=not args.silver_only,
            )
        )
    finally:
        spark.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
