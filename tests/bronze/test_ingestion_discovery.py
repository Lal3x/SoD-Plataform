from pathlib import Path

from sod_platform.bronze.ingestion.discovery import discover_files, sha256_file


def test_discover_files_matches_dynamic_names(tmp_path: Path) -> None:
    (tmp_path / "identity_20260923.csv").write_text("id\n1\n")
    (tmp_path / "identity_20260924.csv").write_text("id\n2\n")
    (tmp_path / "other.csv").write_text("id\n3\n")

    assert [
        path.rsplit("/", 1)[-1]
        for path in discover_files("data/raw/identity*.csv", tmp_path)
    ] == []
    assert [
        path.rsplit("/", 1)[-1] for path in discover_files("identity*.csv", tmp_path)
    ] == ["identity_20260923.csv", "identity_20260924.csv"]


def test_sha256_is_content_based(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "renamed.csv"
    first.write_bytes(b"id\n1\n")
    second.write_bytes(b"id\n1\n")
    assert sha256_file(first) == sha256_file(second)
    second.write_bytes(b"id\n2\n")
    assert sha256_file(first) != sha256_file(second)
