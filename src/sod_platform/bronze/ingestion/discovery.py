"""File discovery and stable content hashing."""

from __future__ import annotations

import hashlib
from pathlib import Path

import fsspec


def discover_files(pattern: str, base_dir: Path) -> list[str]:
    """Return matching files through fsspec, supporting local paths and object stores."""
    if "://" not in pattern and not Path(pattern).is_absolute():
        pattern = str(base_dir / pattern)
    filesystem, inner_pattern = fsspec.core.url_to_fs(pattern)
    return sorted(
        filesystem.unstrip_protocol(path)
        for path in filesystem.glob(inner_pattern)
        if filesystem.isfile(path)
    )


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute a streaming SHA-256 digest through the configured fsspec backend."""
    digest = hashlib.sha256()
    filesystem, inner_path = fsspec.core.url_to_fs(str(path))
    with filesystem.open(inner_path, "rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()
