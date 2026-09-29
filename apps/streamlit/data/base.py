"""Small Spark adapter; pages never access Spark directly."""

from __future__ import annotations

from functools import cached_property
from typing import Any

from apps.streamlit.config import ROOT


class ContractError(RuntimeError):
    """A persisted table does not meet the dashboard contract."""


class SparkSource:
    def __init__(self, spark: Any | None = None):
        self._spark = spark

    @cached_property
    def spark(self):
        if self._spark is not None:
            return self._spark
        from sod_platform.bronze.ingestion.spark import create_spark_session

        return create_spark_session(ROOT, "sod-streamlit-v2-read-only")

    def table(self, name: str, required: set[str] | None = None):
        if not self.spark.catalog.tableExists(name):
            raise ContractError(f"Tabela indisponível: {name}")
        frame = self.spark.table(name)
        missing = (required or set()) - set(frame.columns)
        if missing:
            raise ContractError(f"Contrato incompleto em {name}: {', '.join(sorted(missing))}")
        return frame

    @staticmethod
    def records(frame, limit: int = 500) -> list[dict]:
        return [row.asDict(recursive=True) for row in frame.limit(limit).collect()]
