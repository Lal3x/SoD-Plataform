"""Maintenance operations for the local Iceberg warehouse."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

WAREHOUSE_LAYER_DIRS = ("bronze", "silver", "sot", "sor", "spec")


class UnsafeWarehousePath(ValueError):
    """Raised when cleanup is pointed at a path that is unsafe to remove."""


@dataclass(frozen=True)
class CleanupResult:
    warehouse: Path
    deleted_entries: int


def clean_iceberg_warehouse(warehouse: str | Path) -> CleanupResult:
    """Delete all local files in a dedicated warehouse and recreate empty layers."""
    if "://" in str(warehouse):
        raise UnsafeWarehousePath(
            "Warehouse cleanup supports local filesystem paths only"
        )

    candidate = Path(warehouse).expanduser()
    if candidate.is_symlink():
        raise UnsafeWarehousePath(f"Refusing cleanup of a symlink: {candidate}")
    target = candidate.resolve()
    if target == Path(target.anchor) or "warehouse" not in target.name.lower():
        raise UnsafeWarehousePath(
            f"Refusing cleanup: path must be a dedicated *warehouse directory: {target}"
        )
    deleted_entries = sum(1 for item in target.rglob("*")) if target.exists() else 0
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    for layer in WAREHOUSE_LAYER_DIRS:
        (target / layer).mkdir(exist_ok=True)
    return CleanupResult(warehouse=target, deleted_entries=deleted_entries)
