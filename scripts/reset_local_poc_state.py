"""Safely reset locally generated POC state while preserving V2 sources.

This is deliberately a catalog-aware operation: tables are dropped through
Spark/Iceberg first, rather than deleting the warehouse as a primary action.
"""
from __future__ import annotations

import argparse
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sod_platform.bronze.ingestion.config import load_sources
from sod_platform.bronze.ingestion.spark import create_spark_session
from sod_platform.common.env import load_project_env

ALLOWED_ENVIRONMENTS = {"local", "development", "dev"}
PROJECT_NAMESPACES = {"bronze", "silver", "access_intelligence", "evidence", "policy", "risk", "gold", "validation"}
SOURCE_DOMAINS = {"identity_directory", "access_certifications", "access_requests", "access_assignments", "application_catalog", "identity_master", "entitlements"}


def _inside(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"unsafe path outside allowed root: {resolved}")
    return resolved


def _paths(root: Path) -> list[Path]:
    candidates = [root / "logs", root / ".airflow" / "logs", root / "data" / "spark-tmp", root / "data" / "checkpoints"]
    return [_inside(path, root) for path in candidates if path.exists()]


def _inventory(spark) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for namespace_row in spark.sql("SHOW NAMESPACES IN sod").collect():
        namespace = namespace_row[0]
        if namespace not in PROJECT_NAMESPACES:
            continue
        for table_row in spark.sql(f"SHOW TABLES IN sod.{namespace}").collect():
            table = table_row.tableName
            qualified = f"sod.{namespace}.{table}"
            location = "N/A"
            try:
                detail = spark.sql(f"DESCRIBE TABLE EXTENDED {qualified}").collect()
                metadata = {row.col_name: row.data_type for row in detail if row.col_name in {"Location", "location"}}
                location = metadata.get("Location", metadata.get("location", "N/A"))
            except Exception:
                location = "UNAVAILABLE (stale metadata)"
            snapshot = ""
            try:
                snapshot_row = spark.sql(f"SELECT snapshot_id FROM {qualified}.snapshots ORDER BY committed_at DESC LIMIT 1").first()
                snapshot = str(snapshot_row[0]) if snapshot_row else ""
            except Exception:  # namespace metadata or non-Iceberg object
                snapshot = "N/A"
            rows.append({"catalog": "sod", "namespace": namespace, "table": table, "location": location, "snapshot": snapshot})
    return sorted(rows, key=lambda row: (row["namespace"], row["table"]))


def _write_inventory(path: Path, rows: list[dict[str, str]]) -> None:
    lines = ["# Proof-of-fire pre-reset inventory", "", f"Generated UTC: {datetime.now(timezone.utc).isoformat()}", "", "| catalog | namespace | table | location | current snapshot |", "|---|---|---|---|---|"]
    lines.extend(f"| {r['catalog']} | {r['namespace']} | {r['table']} | {r['location']} | {r['snapshot']} |" for r in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    load_project_env(root)
    environment = os.getenv("SOD_ENV", "").lower()
    if environment not in ALLOWED_ENVIRONMENTS:
        parser.error("reset is allowed only with SOD_ENV=local (or development/dev)")
    sources = load_sources(root / "configs" / "sources.yml")
    found = {source.source_name for source in sources if list(root.glob(source.path))}
    if found != SOURCE_DOMAINS:
        parser.error(f"V2 source guard failed: found={sorted(found)}")
    spark = create_spark_session(root, "sod-local-proof-of-fire-reset")
    try:
        inventory = _inventory(spark)
        inventory_path = root / "artifacts" / "validation" / "proof-of-fire-pre-reset-inventory.md"
        # Do not replace the useful pre-reset evidence with an empty inventory
        # when a later zero-state dry run is performed.
        if inventory or not inventory_path.exists():
            _write_inventory(inventory_path, inventory)
        clean_paths = _paths(root)
        print("tables to drop:", [f"sod.{r['namespace']}.{r['table']}" for r in inventory])
        print("directories to clean:", [str(path) for path in clean_paths])
        print("files to preserve: V2 raw source domains", sorted(SOURCE_DOMAINS))
        print("inventory:", inventory_path)
        if args.dry_run:
            return 0
        for row in inventory:
            qualified = f"sod.{row['namespace']}.{row['table']}"
            try:
                spark.sql(f"DROP TABLE {qualified} PURGE")
            except Exception:
                # HadoopCatalog versions without PURGE still remove table metadata/data
                # through the catalog-aware DROP TABLE implementation.
                spark.sql(f"DROP TABLE {qualified}")
        for path in clean_paths:
            # Keep mount/config directories; only generated contents are deleted.
            for child in path.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        remaining = _inventory(spark)
        if remaining:
            raise RuntimeError(f"reset incomplete; remaining tables: {remaining}")
        print("reset complete: generated Iceberg tables=0; V2 sources preserved")
        return 0
    finally:
        spark.stop()


if __name__ == "__main__":
    raise SystemExit(main())
