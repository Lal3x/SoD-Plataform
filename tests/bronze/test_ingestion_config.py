from pathlib import Path

import pytest

from sod_platform.bronze.ingestion.config import ConfigurationError, load_sources

ROOT = Path(__file__).resolve().parents[2]


def test_loads_configured_sources_without_gabarito() -> None:
    sources = load_sources(ROOT / "configs" / "sources.yml")
    assert {source.source_name for source in sources} == {
        "identity_master",
        "identity_directory",
        "application_catalog",
        "entitlements",
        "access_assignments",
        "access_certifications",
        "access_requests",
    }
    assert all(source.target_table.startswith("sod.bronze.") for source in sources)
    assert all("gabarito" not in source.path for source in sources)


def test_rejects_invalid_target_table(tmp_path: Path) -> None:
    config = tmp_path / "sources.yml"
    config.write_text(
        "sources:\n  bad:\n    source_name: bad\n    path: x.csv\n    format: csv\n    target_table: bronze.bad\n"
    )
    with pytest.raises(ConfigurationError, match="catalog.namespace.table"):
        load_sources(config)
