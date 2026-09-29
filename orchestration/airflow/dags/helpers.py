"""Airflow orchestration helpers; no SoD decision logic."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from airflow.exceptions import AirflowFailException

ROOT = Path("/opt/sod-platform")
LOT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def validate_runtime_params(lote: str, data_ingestao: str) -> None:
    if not LOT_RE.fullmatch(lote):
        raise AirflowFailException("lote must be a safe identifier")
    try:
        date.fromisoformat(data_ingestao)
    except ValueError as exc:
        raise AirflowFailException("data_ingestao must use YYYY-MM-DD") from exc
    if (
        not (ROOT / "data/raw/v2").exists()
        or not (ROOT / "configs/sources.yml").exists()
    ):
        raise AirflowFailException(
            "complete V2 source bundle/configuration unavailable"
        )
