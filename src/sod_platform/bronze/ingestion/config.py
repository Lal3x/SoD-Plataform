"""Load and validate source ingestion configuration."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigurationError(ValueError):
    """Raised when source configuration is invalid."""


@dataclass(frozen=True)
class SourceConfig:
    source_name: str
    path: str
    format: str
    target_table: str
    strategy: str
    schema_behavior: str
    options: dict[str, Any]
    required_columns: list[str] = field(default_factory=list)


def load_sources(path: Path) -> list[SourceConfig]:
    """Load configured sources from YAML and validate required properties."""
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigurationError(
            f"Unable to read source configuration {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), dict):
        raise ConfigurationError("Configuration must contain a 'sources' mapping")

    configs = []
    for key, value in payload["sources"].items():
        if not isinstance(value, dict):
            raise ConfigurationError(f"Source {key!r} must be a mapping")
        source_name = value.get("source_name", key)
        source_path = value.get("path")
        file_format = str(value.get("format", "")).lower()
        target = value.get("target_table")
        strategy = value.get("strategy", "append")
        schema_behavior = value.get("schema_behavior", "additive")
        if not source_name or not source_path or not target:
            raise ConfigurationError(
                f"Source {key!r} requires source_name, path and target_table"
            )
        if file_format not in {"csv", "json", "parquet", "xlsx"}:
            raise ConfigurationError(f"Unsupported format {file_format!r} for {key!r}")
        if strategy != "append":
            raise ConfigurationError(f"Unsupported strategy {strategy!r} for {key!r}")
        if schema_behavior not in {"additive", "strict"}:
            raise ConfigurationError(
                f"Unsupported schema_behavior {schema_behavior!r} for {key!r}"
            )
        if not re.fullmatch(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*){2}", str(target)):
            raise ConfigurationError(
                f"Target table must be a catalog.namespace.table identifier: {target!r}"
            )
        options = value.get("options", {})
        if not isinstance(options, dict):
            raise ConfigurationError(f"Options for {key!r} must be a mapping")
        required = value.get("required_columns", [])
        if not isinstance(required, list) or not all(
            isinstance(c, str) for c in required
        ):
            raise ConfigurationError("required_columns must be a list of column names")
        if "gabarito" in str(source_path) or "tests/fixtures" in str(source_path):
            raise ConfigurationError("Validation fixtures are not ingestion sources")
        configs.append(
            SourceConfig(
                str(source_name),
                str(source_path),
                file_format,
                str(target),
                strategy,
                schema_behavior,
                options,
                value.get("required_columns", []),
            )
        )
    return configs
