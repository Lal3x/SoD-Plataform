"""IAM boundaries independent of labels: pending requests, multiple accounts and FK failures."""

from datetime import date
from pathlib import Path

import pytest
import yaml
from pyspark.sql import functions as F

from sod_platform.access_intelligence.context.engine import build_access_context
from sod_platform.silver.contract import INPUT_SCHEMAS, OPTIONAL_COLUMNS
from sod_platform.silver.preparation import prepare_silver

ROOT = Path(__file__).resolve().parents[2]


def iam_inputs(spark):
    rows = {
        "identity_master": [
            {
                "identidade_id": "I1",
                "comunidade": "Credito",
                "squad": "S",
                "cargo": "analista",
                "tipo_identidade": "employee",
                "gestor": "G",
                "data_entrada_comunidade_atual": "2024-02-01",
                "status_identidade": "active",
            }
        ],
        "iga_entitlements": [
            {
                "entitlement_id": "E1",
                "sigla_id": "A1",
                "comunidade_dona_sigla": "Credito",
                "birthright": "true",
                "sigla_publica": "false",
                "application_owner": "G",
                "criticidade": "HIGH",
                "classificacao_dado": "INTERNAL",
                "privileged": "false",
                "regulatory_scope": "NONE",
            }
        ],
        "application_catalog": [
            {
                "sigla_id": "A1",
                "nome_sistema": "App",
                "owner": "G",
                "comunidade": "Credito",
                "criticidade": "HIGH",
                "classificacao_dado": "INTERNAL",
                "privileged": "false",
                "regulatory_scope": "NONE",
            }
        ],
        "iga_access_assignments": [
            {
                "identidade_id": "I1",
                "entitlement_id": "E1",
                "data_concessao": "2024-01-01",
                "tipo_atribuicao": "atribuido",
            }
        ],
        "iga_access_requests": [
            {
                "request_id": f"R{n}",
                "identidade_id": "I1",
                "entitlement_id": "E1",
                "solicitante": "G",
                "data_solicitacao": "2023-12-01",
                "status_solicitacao": status,
                "data_aprovacao": "2023-12-02" if status == "APPROVED" else None,
                "aprovador": "G" if status == "APPROVED" else None,
            }
            for n, status in enumerate(["APPROVED", "PENDING", "REJECTED"])
        ],
        "identity_directory": [
            {
                "account_id": f"C{n}",
                "identidade_id": "I1",
                "status_conta": "active",
                "tipo_conta": "employee",
                "data_criacao": "2023-01-01",
                "ultima_autenticacao": "2024-01-15",
            }
            for n in range(2)
        ],
        "access_certifications": [
            {
                "campaign_id": f"P{n}",
                "identidade_id": "I1",
                "entitlement_id": "E1",
                "data_revisao": dt,
                "decisao": decision,
                "revisor": "G",
            }
            for n, (dt, decision) in enumerate(
                [
                    ("2024-01-10", "MAINTAIN"),
                    ("2024-02-10", "REVOKE"),
                    ("2026-01-01", "MAINTAIN"),
                    (None, "PENDING"),
                ]
            )
        ],
    }
    raw = {}
    rows["identity_directory"].append(
        {
            "account_id": "SERVICE",
            "tipo_conta": "service",
            "status_conta": "active",
            "data_criacao": "2023-01-01",
        }
    )
    for name, records in rows.items():
        columns = [
            c for c in INPUT_SCHEMAS[name] if c not in OPTIONAL_COLUMNS.get(name, set())
        ]
        raw[name] = spark.createDataFrame(
            records, ", ".join(f"{c} string" for c in columns)
        )
        raw[name] = (
            raw[name]
            .withColumn("_ingestion_id", F.lit("fixture"))
            .withColumn("_source_file", F.lit(name))
        )
    config = yaml.safe_load((ROOT / "configs/data_quality.yml").read_text())
    return raw, config


def test_pending_requests_and_context_cardinality(spark):
    raw, config = iam_inputs(spark)
    cached = []
    try:
        valid, rejected, _ = prepare_silver(raw, config, "iam", cached=cached)
        assert sum(r.count() for r in rejected) == 0
        assert valid["iga_access_requests"].count() == 3
        assert (
            valid["identity_directory"]
            .where("tipo_conta='service' AND identidade_id IS NULL")
            .count()
            == 1
        )
        context = build_access_context(valid, date(2025, 2, 1))
        row = context.first()
        assert context.count() == 1
        assert row.account_count == 2 and len(row.accounts) == 2
        assert row.certification_decisao == "REVOKE"
        assert row.certification_pending_count == 1
        assert valid["access_certifications"].where("decisao='PENDING'").count() == 1
        assert row.approval_exists and row.never_used and row.inherited_access
        assert row.approval_linkage_quality == "STRONG_INFERRED"
        assert row.days_since_last_use is None
        assert row.grant_id.startswith("technical-")
        assert row.grant_id_generated is True
        assert len(context.columns) == len(set(context.columns))
        unapproved = {
            **valid,
            "iga_access_requests": valid["iga_access_requests"].where(
                "status_solicitacao <> 'APPROVED'"
            ),
        }
        assert (
            build_access_context(unapproved, date(2025, 2, 1)).first().approval_exists
            is False
        )
        temporally_incoherent = {
            **valid,
            "iga_access_requests": valid["iga_access_requests"].withColumn(
            "data_aprovacao", F.lit("2026-01-01").cast("date")
            ),
        }
        assert (
            build_access_context(temporally_incoherent, date(2025, 2, 1)).first().approval_exists
            is False
        )
    finally:
        for frame in cached:
            frame.unpersist()


def test_directory_certification_foreign_keys_and_status_domains(spark):
    raw, config = iam_inputs(spark)
    raw["identity_directory"] = raw["identity_directory"].withColumn(
        "identidade_id", F.lit("missing")
    )
    raw["access_certifications"] = raw["access_certifications"].withColumn(
        "entitlement_id", F.lit("missing")
    )
    raw["iga_access_requests"] = raw["iga_access_requests"].withColumn(
        "status_solicitacao", F.lit("UNKNOWN")
    )
    cached = []
    try:
        valid, rejected, _ = prepare_silver(raw, config, "invalid", cached=cached)
        assert valid["identity_directory"].count() == 0
        assert valid["access_certifications"].count() == 0
        assert valid["iga_access_requests"].count() == 0
        reasons = {
            r.error_code
            for df in rejected
            for r in df.select("error_code").distinct().collect()
        }
        assert {
            "INVALID_IDENTITY_REFERENCE",
            "INVALID_ENTITLEMENT_REFERENCE",
            "INVALID_DOMAIN",
        } <= reasons
        assert sum(df.count() for df in raw.values()) == sum(
            df.count() for df in valid.values()
        ) + sum(df.count() for df in rejected)
    finally:
        for frame in cached:
            frame.unpersist()


def test_failed_publication_audits_only_committed_tables(spark, tmp_path, monkeypatch):
    from sod_platform.silver import pipeline

    raw, config = iam_inputs(spark)
    config["tables"] = {name: f"sod.bronze.failure_{name}" for name in raw}
    spark.sql("CREATE NAMESPACE IF NOT EXISTS sod.bronze")
    for name, frame in raw.items():
        frame.writeTo(config["tables"][name]).using("iceberg").createOrReplace()
    path = tmp_path / "config.yml"
    path.write_text(yaml.safe_dump(config))

    def fail_write(*args):
        raise RuntimeError("simulated before publication")

    monkeypatch.setattr(pipeline, "_write_snapshot", fail_write)
    with pytest.raises(RuntimeError, match="before publication"):
        pipeline.run_silver(spark, path, date(2025, 2, 1))
    last = (
        spark.table("sod.metadata.silver_runs")
        .where("status <> 'started'")
        .orderBy(F.desc("started_at"))
        .first()
    )
    assert last.status == "failed" and last.records_written == 0
