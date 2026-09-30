"""Command line entry point for the Bronze ingestion pipeline."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from sod_platform.bronze.ingestion.config import ConfigurationError, load_sources
from sod_platform.bronze.ingestion.spark import (
    SparkPrerequisiteError,
    create_spark_session,
)
from sod_platform.bronze.maintenance import clean_iceberg_warehouse
from sod_platform.bronze.pipeline import run_bronze
from sod_platform.common.env import load_project_env
from sod_platform.observability.logging import configure_logging


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest configured source files into Bronze Iceberg tables"
    )
    parser.add_argument("--config", type=Path, default=Path("configs/sources.yml"))
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path.cwd(),
        help="Resolve relative source paths from this directory",
    )
    parser.add_argument(
        "--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR")
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="Operational log path (default: logs/bronze/ingestion.log)",
    )
    parser.add_argument(
        "--clean-warehouse",
        action="store_true",
        help="Delete generated Iceberg data from the local warehouse",
    )
    parser.add_argument(
        "--warehouse",
        type=Path,
        help="Local warehouse path to clean (defaults to SOD_WAREHOUSE or data/warehouse)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm the destructive warehouse cleanup",
    )
    args = parser.parse_args()
    base_dir = args.base_dir.resolve()
    load_project_env(base_dir)
    log_file = args.log_file or Path(
        os.getenv("SOD_LOG_FILE", base_dir / "logs" / "bronze" / "ingestion.log")
    )
    configure_logging(log_file, getattr(logging, args.log_level))
    if args.clean_warehouse:
        if not args.yes:
            parser.error(
                "--clean-warehouse requires --yes to confirm deleting Iceberg data"
            )
        configured_warehouse = args.warehouse or os.getenv(
            "SOD_WAREHOUSE", str(base_dir / "data" / "warehouse")
        )
        configured_warehouse = Path(configured_warehouse).expanduser()
        if not configured_warehouse.is_absolute():
            configured_warehouse = base_dir / configured_warehouse
        try:
            result = clean_iceberg_warehouse(configured_warehouse)
        except ValueError as exc:
            logging.getLogger(__name__).error("Warehouse cleanup rejected: %s", exc)
            return 2
        logging.getLogger(__name__).warning(
            "iceberg_warehouse_cleaned path=%s deleted_entries=%d",
            result.warehouse,
            result.deleted_entries,
        )
        print(
            f"Iceberg warehouse limpo: {result.warehouse} "
            f"({result.deleted_entries} itens removidos)"
        )
        return 0

    if args.yes or args.warehouse:
        parser.error("--yes e --warehouse só podem ser usados com --clean-warehouse")

    config_path = args.config if args.config.is_absolute() else base_dir / args.config
    try:
        sources = load_sources(config_path)
    except ConfigurationError as exc:
        logging.getLogger(__name__).error("Configuration error: %s", exc)
        return 2
    try:
        spark = create_spark_session(base_dir)
    except SparkPrerequisiteError as exc:
        logging.getLogger(__name__).error("Spark prerequisite error: %s", exc)
        return 2
    try:
        metrics = run_bronze(spark, sources, base_dir)
        print(metrics)
        return 1 if metrics.get("files_failed", 0) else 0
    finally:
        spark.stop()


if __name__ == "__main__":
    raise SystemExit(main())
