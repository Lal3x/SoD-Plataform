"""Explicit entrypoint for offline peer discovery experiments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sod_platform.bronze.ingestion.spark import create_spark_session
from sod_platform.common.env import load_project_env
from sod_platform.observability.logging import configure_logging

from .nmf_hdbscan_runner import run_nmf_hdbscan_shadow
from .pipeline import run_lda_shadow


def main() -> int:
    parser = argparse.ArgumentParser(description="Run experimental peer discovery shadows")
    parser.add_argument("command", choices=("lda-shadow", "nmf-hdbscan-shadow"))
    parser.add_argument("--config", type=Path, default=Path("configs/access_intelligence.yml"))
    parser.add_argument("--log-file", type=Path, default=Path("logs/access_intelligence/peer_discovery.log"))
    args = parser.parse_args()
    root = Path.cwd()
    load_project_env(root)
    configure_logging(args.log_file)
    spark = create_spark_session(root, "sod-platform-peer-discovery")
    try:
        runner = run_lda_shadow if args.command == "lda-shadow" else run_nmf_hdbscan_shadow
        print(json.dumps(runner(spark, root / args.config), default=str, sort_keys=True))
        return 0
    finally:
        spark.stop()


if __name__ == "__main__":
    raise SystemExit(main())
