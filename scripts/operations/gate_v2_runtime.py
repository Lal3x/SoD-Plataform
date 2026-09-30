"""Small operational gates for materialized runtime stages; no transformations."""

from __future__ import annotations

import argparse
from pathlib import Path

from sod_platform.bronze.ingestion.spark import create_spark_session
from sod_platform.common.env import load_project_env

GATES = {
    "bronze": [
        "sod.bronze.identity_master",
        "sod.bronze.identity_directory",
        "sod.bronze.entitlements",
        "sod.bronze.access_assignments",
        "sod.bronze.access_requests",
        "sod.bronze.access_certifications",
        "sod.bronze.application_catalog",
    ],
    "silver": [
        "sod.silver.identity_master",
        "sod.silver.identity_directory",
        "sod.silver.iga_entitlements",
        "sod.silver.iga_access_assignments",
        "sod.silver.iga_access_requests",
        "sod.silver.access_certifications",
    ],
    "gold": ["sod.gold.sod_assessment_gold001"],
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=GATES)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    load_project_env(root)
    spark = create_spark_session(root, f"sod-v2-gate-{args.stage}")
    try:
        absent = [
            table for table in GATES[args.stage] if not spark.catalog.tableExists(table)
        ]
        empty = [
            table
            for table in GATES[args.stage]
            if table not in absent and spark.table(table).limit(1).count() == 0
        ]
        if absent or empty:
            raise RuntimeError(
                f"gate {args.stage} failed: absent={absent}, empty={empty}"
            )
        print(f"gate {args.stage} passed")
        return 0
    finally:
        spark.stop()


if __name__ == "__main__":
    raise SystemExit(main())
