from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from sod_platform.bronze.ingestion.config import SourceConfig
from sod_platform.bronze.pipeline import run_bronze


def test_iceberg_write_lineage_idempotency_schema_evolution_and_failures(
    spark, tmp_path: Path
) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "users_1.csv").write_text("id,name\n1,Ana\n", encoding="utf-8")
    source = SourceConfig(
        "users",
        "raw/users*.csv",
        "csv",
        "sod.bronze.test_users",
        "append",
        "additive",
        {"header": "true"},
    )

    first = run_bronze(spark, [source], tmp_path)
    assert first["files_processed"] == 1
    table = spark.table(source.target_table)
    row = table.first()
    assert row["id"] == "1"
    assert row["_source_name"] == "users"
    assert row["_source_file_hash"]
    assert row["_ingestion_id"]

    assert run_bronze(spark, [source], tmp_path)["files_skipped"] == 1
    audit = spark.table("sod.metadata.ingestion_runs")
    successful_run = audit.where(
        "source_name = 'users' AND status = 'SUCCEEDED'"
    ).first()
    assert successful_run["batch_id"]
    assert successful_run["started_at"] is not None
    assert successful_run["finished_at"] is not None
    assert successful_run["duration_seconds"] >= 0
    assert successful_run["source_file"].endswith("users_1.csv")
    assert successful_run["records_received"] == 1
    assert successful_run["records_written"] == 1
    assert audit.where("source_name = 'users' AND status = 'SKIPPED'").count() == 1

    (raw / "users_2.csv").write_text(
        "id,name,department\n2,Bia,Finance\n", encoding="utf-8"
    )
    evolved = run_bronze(spark, [source], tmp_path)
    assert evolved["files_processed"] == 1
    assert "department" in spark.table(source.target_table).columns
    assert spark.table(source.target_table).count() == 2

    (raw / "users_3.csv").write_text('"unterminated\n', encoding="utf-8")
    failed = run_bronze(spark, [source], tmp_path)
    assert failed["files_failed"] == 1
    assert audit.where("status = 'FAILED'").count() == 1
    failed_run = audit.where("status = 'FAILED'").first()
    assert failed_run["ingestion_id"]
    assert failed_run["error_category"] == "read"
    assert failed_run["error_message"]


def test_incompatible_schema_is_recorded(spark, tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    source = SourceConfig(
        "changing",
        "raw/change*.parquet",
        "parquet",
        "sod.bronze.test_schema_change",
        "append",
        "additive",
        {},
    )
    pq.write_table(pa.table({"id": [1]}), raw / "change_1.parquet")
    run_bronze(spark, [source], tmp_path)
    pq.write_table(pa.table({"id": ["text"]}), raw / "change_2.parquet")
    result = run_bronze(spark, [source], tmp_path)
    assert result["files_failed"] == 1
    assert (
        spark.table("sod.metadata.ingestion_runs")
        .where("source_name = 'changing' AND status = 'FAILED'")
        .count()
        == 1
    )


def test_business_nulls_reused_name_and_corrected_retry(spark, tmp_path):
    from datetime import date

    path = tmp_path / "grants.parquet"
    source = SourceConfig(
        "grants",
        "*.parquet",
        "parquet",
        "sod.bronze.test_grants",
        "append",
        "additive",
        {},
    )
    schema = pa.schema(
        [
            ("batch_id", pa.string()),
            ("source_system", pa.string()),
            ("source_name", pa.string()),
            ("extract_timestamp", pa.string()),
            ("grant_id", pa.string()),
            ("request_id", pa.string()),
            ("ultimo_uso", pa.date32()),
            ("data_aprovacao", pa.date32()),
        ]
    )
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "batch_id": "upstream-batch",
                    "source_system": "IGA",
                    "source_name": "original-name",
                    "extract_timestamp": "2025-01-01T00:00:00-03:00",
                    "grant_id": "g1",
                    "request_id": None,
                    "ultimo_uso": None,
                    "data_aprovacao": None,
                }
            ],
            schema=schema,
        ),
        path,
    )
    assert run_bronze(spark, [source], tmp_path)["files_processed"] == 1
    row = spark.table(source.target_table).first()
    assert row.grant_id == "g1"
    assert row.batch_id == "upstream-batch"
    assert row.source_system == "IGA"
    assert row.source_name == "original-name"
    assert row.extract_timestamp == "2025-01-01T00:00:00-03:00"
    assert row._source_name == "grants"
    assert (
        row.request_id is None and row.ultimo_uso is None and row.data_aprovacao is None
    )
    path.write_bytes(b"not parquet")
    assert run_bronze(spark, [source], tmp_path)["files_failed"] == 1
    assert (
        spark.table("sod.metadata.bronze_quarantine")
        .where("source_name='grants'")
        .count()
        == 1
    )
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "grant_id": "g2",
                    "request_id": "r2",
                    "ultimo_uso": date(2025, 1, 1),
                    "data_aprovacao": None,
                }
            ],
            schema=schema,
        ),
        path,
    )
    assert run_bronze(spark, [source], tmp_path)["files_processed"] == 1
    assert run_bronze(spark, [source], tmp_path)["files_skipped"] == 1
    assert spark.table(source.target_table).count() == 2


def test_write_failure_and_lost_audit_do_not_duplicate(spark, tmp_path, monkeypatch):
    from sod_platform.bronze import pipeline
    from sod_platform.bronze.ingestion import ingestion

    (tmp_path / "one.csv").write_text("id\n1\n")
    source = SourceConfig(
        "commit_test",
        "*.csv",
        "csv",
        "sod.bronze.test_commit",
        "append",
        "additive",
        {"header": "true"},
    )
    append = ingestion.append_iceberg

    def fail_write(*args):
        raise RuntimeError("simulated before commit")

    monkeypatch.setattr(ingestion, "append_iceberg", fail_write)
    result = run_bronze(spark, [source], tmp_path)
    assert result["records_received"] == 1 and result["records_written"] == 0
    assert result["files_failed"] == 1
    monkeypatch.setattr(ingestion, "append_iceberg", append)
    audit = pipeline.write_runs

    def fail_audit(session, records, *args):
        if any(r["status"] == "SUCCEEDED" for r in records):
            raise RuntimeError("simulated after commit")
        audit(session, records, *args)

    monkeypatch.setattr(pipeline, "write_runs", fail_audit)
    import pytest

    with pytest.raises(RuntimeError, match="after commit"):
        run_bronze(spark, [source], tmp_path)
    monkeypatch.setattr(pipeline, "write_runs", audit)
    assert run_bronze(spark, [source], tmp_path)["files_skipped"] == 1
    assert spark.table(source.target_table).count() == 1


def test_group_commit_preserves_file_lineage_and_replay(spark, tmp_path):
    import json

    for index in range(3):
        (tmp_path / f"file {index}.json").write_text(
            json.dumps(
                [{"id": str(index), "ultimo_uso": None, "batch_id": f"b{index}"}]
            )
        )
    # Duplicate bytes within the same arrival must not be committed twice.
    (tmp_path / "copy.json").write_bytes((tmp_path / "file 0.json").read_bytes())
    (tmp_path / "invalid.json").write_text("{broken")
    source = SourceConfig(
        "grouped",
        "*.json",
        "json",
        "sod.bronze.test_grouped",
        "append",
        "additive",
        {"multiLine": "true"},
    )
    result = run_bronze(spark, [source], tmp_path)
    assert (
        result["files_processed"],
        result["files_skipped"],
        result["files_failed"],
    ) == (3, 1, 1)
    rows = spark.table(source.target_table).collect()
    assert {r.id for r in rows} == {"0", "1", "2"}
    assert len({r._ingestion_id for r in rows}) == 3
    assert all(r.ultimo_uso is None and r.batch_id == f"b{r.id}" for r in rows)
    assert spark.table(source.target_table + ".snapshots").count() == 1
    audit = (
        spark.table("sod.metadata.ingestion_runs")
        .where("source_name='grouped' AND status='SUCCEEDED'")
        .collect()
    )
    assert {r.source_file_hash for r in audit} == {r._source_file_hash for r in rows}
    assert sum(r.records_written for r in audit) == 3
    result = run_bronze(spark, [source], tmp_path)
    assert result["files_skipped"] == 4 and result["files_failed"] == 1
    assert spark.table(source.target_table).count() == 3
    assert spark.table(source.target_table + ".snapshots").count() == 1


def test_group_read_failure_isolates_corrupt_parquet(spark, tmp_path):
    good = tmp_path / "a.parquet"
    bad = tmp_path / "b.parquet"
    pq.write_table(pa.table({"id": ["good"]}), good, compression="NONE")
    pq.write_table(pa.table({"id": ["bad"]}), bad, compression="NONE")
    content = bytearray(bad.read_bytes())
    footer_size = int.from_bytes(content[-8:-4], "little")
    # Retain valid footer/schema but corrupt the data pages: failure is lazy.
    footer_start = len(content) - footer_size - 8
    content[4:footer_start] = b"\x00" * (footer_start - 4)
    bad.write_bytes(content)
    source = SourceConfig(
        "split",
        "*.parquet",
        "parquet",
        "sod.bronze.test_split",
        "append",
        "additive",
        {},
    )
    result = run_bronze(spark, [source], tmp_path)
    assert result["files_processed"] == 1 and result["files_failed"] == 1
    assert result["records_written"] == 1
    assert spark.table(source.target_table).first().id == "good"
    failed = (
        spark.table("sod.metadata.bronze_quarantine")
        .where("source_name='split'")
        .first()
    )
    assert failed.source_file.endswith("b.parquet")
    assert failed.error_category == "read" and failed.records_written == 0
