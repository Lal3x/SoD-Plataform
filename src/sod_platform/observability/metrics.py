"""Counters and duration summary for one Bronze batch."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class BatchMetrics:
    """Operational data quality metrics aggregated across a batch."""

    batch_id: str
    files_discovered: int = 0
    files_processed: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    records_received: int = 0
    records_written: int = 0
    bytes_discovered: int = 0
    bytes_processed: int = 0
    audit_failures: int = 0
    duration_seconds: float = 0.0

    def as_dict(self) -> dict[str, str | int | float]:
        """Return metrics as a serializable mapping."""
        return asdict(self)
