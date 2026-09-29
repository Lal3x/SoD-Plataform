"""Boundary fixtures independent from synthetic labels and risk decisions."""

import json
from datetime import date

import pytest
from pyspark.sql import functions as F

from sod_platform.access_intelligence.context.engine import build_access_context
from sod_platform.silver.contract import SCHEMAS
from sod_platform.silver.preparation import prepare_silver
from sod_platform.silver.transform import parse_date


@pytest.fixture(scope="module")
def prepared(spark):
    def identity(key, community=" CREDITO ", kind="EMPLOYEE", entry="2024-02-01"):
        return (key, community, "squad", "cargo", kind, "gestor", entry)

    records = {
        "identities": [
            identity("I1"),
            identity("I1"),
            identity("I2", entry=None),
            identity(None),
            identity("blank", community="   "),
            identity("bad-domain", kind="robot"),
            identity("bad-date", entry="31/02/2024"),
            identity("conflict"),
            identity("conflict", community="Tecnologia"),
        ],
        "entitlements": [
            (
                "E1",
                "SIG1",
                "tecnologia",
                "sim",
                "true",
                "OWNER",
                "HIGH",
                "INTERNAL",
                "false",
                "NONE",
            ),
            (
                "E2",
                "SIG2",
                "Credito",
                "0",
                "não",
                "OWNER",
                "LOW",
                "INTERNAL",
                "false",
                "NONE",
            ),
            (
                None,
                "SIG3",
                "Credito",
                "true",
                "false",
                "OWNER",
                "LOW",
                "INTERNAL",
                "false",
                "NONE",
            ),
            (
                "bad-bool",
                "SIG3",
                "Credito",
                "maybe",
                "true",
                "OWNER",
                "LOW",
                "INTERNAL",
                "false",
                "NONE",
            ),
            (
                "bad-sigla",
                None,
                "Credito",
                "true",
                "false",
                "OWNER",
                "LOW",
                "INTERNAL",
                "false",
                "NONE",
            ),
            (
                "conflict",
                "SIG1",
                "Credito",
                "true",
                "false",
                "OWNER",
                "LOW",
                "INTERNAL",
                "false",
                "NONE",
            ),
            (
                "conflict",
                "SIG2",
                "Credito",
                "true",
                "false",
                "OWNER",
                "LOW",
                "INTERNAL",
                "false",
                "NONE",
            ),
        ],
        "accesses": [
            ("I1", "E1", "01/01/2024", " DETECTADO ", None),
            ("I1", "E1", "2024-01-01", "detectado", None),
            ("I2", "E2", "2024-02-01", "atribuido", "2024-02-05"),
            ("missing", "E1", "2024-01-01", "detectado", None),
            ("I1", "missing", "2024-01-01", "detectado", None),
            ("I1", "E2", "2024-01-01", "detectado", None),
            ("I1", "E2", "2024-01-01", "detectado", None),
            (None, "E1", "2024-01-01", "detectado", None),
            ("I2", "E1", "2024-13-01", "detectado", None),
            ("I2", "E1", "2024-01-01", "root", None),
            ("I2", "E1", "2024-01-01", "detectado", "invalid"),
        ],
        "approvals": [
            ("I1", "E1", "2024-01-01", "Z"),
            ("I1", "E1", "2024-02-01", "B"),
            ("I1", "E1", "2024-02-01", "A"),
            ("I1", "E1", "2024-02-01", "A"),
            ("I2", "E2", "2024-01-01", None),
            ("missing", "E1", "2024-01-01", "A"),
            ("I2", "missing", "2024-01-01", "A"),
            ("I2", "E1", "2024-01-01", "A"),
        ],
    }
    raw = {
        name: spark.createDataFrame(
            rows,
            ", ".join(
                f"{c} string"
                for c in (
                    [
                        *SCHEMAS[name],
                        "application_owner",
                        "criticidade",
                        "classificacao_dado",
                        "privileged",
                        "regulatory_scope",
                    ]
                    if name == "entitlements"
                    else SCHEMAS[name]
                )
            ),
        )
        .withColumn("_source_file", F.lit(f"{name}.source"))
        .withColumn("_ingestion_id", F.lit("bronze-test"))
        for name, rows in records.items()
    }
    config = {
        "tables": {n: f"custom.bronze.{n}" for n in raw},
        "domains": {
            "tipo_identidade": ["employee", "contractor"],
            "tipo_atribuicao": ["detectado", "atribuido"],
        },
        "date_formats": ["yyyy-MM-dd", "dd/MM/yyyy"],
    }
    valid, rejects, _ = prepare_silver(raw, config, "run-test")
    cached = [df.cache() for df in valid.values()]
    rows = {n: df.collect() for n, df in valid.items()}
    rejected = [r for df in rejects for r in df.collect()]
    context = build_access_context(valid, date(2024, 3, 1)).collect()
    yield rows, rejected, context, records, raw, config
    for df in cached:
        df.unpersist()


def test_disposition_accounting_and_referential_integrity(prepared):
    rows, rejected, context, records, *_ = prepared
    assert sum(map(len, records.values())) == sum(map(len, rows.values())) + len(
        rejected
    )
    assert len(rows["identities"]) == 2
    assert len(rows["entitlements"]) == 2
    assert len(rows["accesses"]) == 3
    assert len(rows["approvals"]) == 4
    assert len(context) == 3
    assert {(r.identidade_id, r.entitlement_id) for r in context} == {
        ("I1", "E1"),
        ("I2", "E2"),
        ("I1", "E2"),
    }
    assert len({r.grant_id for r in context}) == len(context)


@pytest.mark.parametrize(
    "code",
    [
        "MISSING_REQUIRED_FIELD",
        "INVALID_DOMAIN",
        "INVALID_DATE",
        "INVALID_BOOLEAN",
        "DUPLICATE_RECORD",
        "DUPLICATE_KEY_CONFLICT",
        "INVALID_IDENTITY_REFERENCE",
        "INVALID_ENTITLEMENT_REFERENCE",
    ],
)
def test_dq_rules_have_traceable_rejections(prepared, code):
    rejected = [r for r in prepared[1] if r.error_code == code]
    assert rejected
    for row in rejected:
        assert row.source_table.startswith("custom.bronze.")
        assert row._silver_run_id == "run-test"
        assert row._ingestion_id == "bronze-test"
        assert row.detected_at is not None
        assert json.loads(row.original_data)["_source_file"] == row._source_file


def test_raw_payload_survives_invalid_boolean(prepared):
    row = next(r for r in prepared[1] if r.error_code == "INVALID_BOOLEAN")
    assert json.loads(row.original_data)["birthright"] == "maybe"


def test_context_derivatives_and_approval_tie_break(prepared):
    rows = {(r.identidade_id, r.entitlement_id): r for r in prepared[2]}
    approved = rows[("I1", "E1")]
    assert approved.comunidade == "Credito"
    assert approved.sigla_publica is True and approved.birthright is True
    assert approved.cross_community is True and approved.approval_exists is True
    assert approved.aprovador == "Z" and approved.data_aprovacao == date(2024, 1, 1)
    assert approved.inherited_access is True and approved.never_used is True
    assert approved.access_age_days == 60 and approved.days_since_last_use is None
    assert json.loads(approved._accesses_lineage)["_ingestion_id"] == "bronze-test"
    other = rows[("I2", "E2")]
    assert other.cross_community is False and other.approval_exists is False
    assert other.inherited_access is None and other.never_used is False
    assert other.access_age_days == 29 and other.days_since_last_use == 25
    assert other.aprovador is None


def test_missing_source_column_fails_explicitly(prepared):
    raw, config = prepared[4:]
    with pytest.raises(ValueError, match="Missing columns in identities"):
        prepare_silver(
            {**raw, "identities": raw["identities"].drop("cargo")}, config, "bad-run"
        )


def test_already_typed_date_and_invalid_input(spark):
    df = spark.createDataFrame([(date(2024, 1, 1),)], "dt date")
    assert parse_date(df, "dt", ["yyyy-MM-dd"]).first().dt == date(2024, 1, 1)


def test_prepare_silver_accepts_iam_iga_contracts(spark):
    raw = {
        "identity_master": spark.createDataFrame(
            [
                (
                    "ID-CRE-0001",
                    "Credito",
                    "nucleo_beta",
                    "analista",
                    "employee",
                    "GESTOR-CRE-01",
                    "2023-01-15",
                    "active",
                    None,
                )
            ],
            "identidade_id string, comunidade string, squad string, cargo string, tipo_identidade string, gestor string, data_entrada_comunidade_atual string, status_identidade string, data_desligamento string",
        ),
        "application_catalog": spark.createDataFrame(
            [
                (
                    "SIG-CRE-01",
                    "Operacao de credito 1",
                    "OWNER-CREDITO",
                    "Credito",
                    "CRITICAL",
                    "RESTRICTED",
                    "False",
                    "BACEN",
                )
            ],
            "sigla_id string, nome_sistema string, owner string, comunidade string, criticidade string, classificacao_dado string, privileged string, regulatory_scope string",
        ),
        "iga_entitlements": spark.createDataFrame(
            [
                (
                    "ENT-CRE-001",
                    "SIG-CRE-01",
                    "Credito",
                    True,
                    False,
                    "OWNER-CREDITO",
                    "CRITICAL",
                    "RESTRICTED",
                    False,
                    "BACEN",
                )
            ],
            "entitlement_id string, sigla_id string, comunidade_dona_sigla string, birthright boolean, sigla_publica boolean, application_owner string, criticidade string, classificacao_dado string, privileged boolean, regulatory_scope string",
        ),
        "iga_access_assignments": spark.createDataFrame(
            [
                (
                    "GR-1",
                    "ID-CRE-0001",
                    "ENT-CRE-001",
                    None,
                    "2024-01-02",
                    None,
                    "active",
                    "direct",
                    None,
                )
            ],
            "grant_id string, identidade_id string, entitlement_id string, request_id string, data_concessao string, data_revogacao string, status_concessao string, tipo_atribuicao string, ultimo_uso string",
        ),
        "iga_access_requests": spark.createDataFrame(
            [
                (
                    "REQ-1",
                    "GR-1",
                    "ID-CRE-0001",
                    "ENT-CRE-001",
                    "GESTOR-CRE-01",
                    "2024-01-01",
                    "APPROVED",
                    "GESTOR-CRE-02",
                    "2024-01-02",
                    "Necessidade operacional",
                )
            ],
            "request_id string, grant_id string, identidade_id string, entitlement_id string, solicitante string, data_solicitacao string, status_solicitacao string, aprovador string, data_aprovacao string, motivo string",
        ),
        "access_certifications": spark.createDataFrame(
            [
                (
                    "CAMP-1",
                    "ID-CRE-0001",
                    "ENT-CRE-001",
                    "2025-01-15",
                    "GESTOR-CRE-02",
                    "MAINTAIN",
                    "Acesso revisado",
                )
            ],
            "campaign_id string, identidade_id string, entitlement_id string, data_revisao string, revisor string, decisao string, justificativa string",
        ),
        "identity_directory": spark.createDataFrame(
            [
                (
                    "ACC-ID-CRE-0001",
                    "ID-CRE-0001",
                    "active",
                    "employee",
                    "2020-01-01",
                    "2025-01-30",
                    None,
                )
            ],
            "account_id string, identidade_id string, status_conta string, tipo_conta string, data_criacao string, ultima_autenticacao string, data_bloqueio string",
        ),
    }
    config = {
        "tables": {name: f"bronze.{name}" for name in raw},
        "domains": {
            "tipo_identidade": ["employee", "contractor"],
            "tipo_conta": ["employee", "contractor", "service"],
            "status_conta": ["active", "disabled", "locked"],
            "status_concessao": ["active"],
            "status_solicitacao": ["APPROVED", "REJECTED", "PENDING"],
            "decisao": ["MAINTAIN", "REVOKE", "PENDING"],
            "tipo_atribuicao": ["direct"],
        },
        "date_formats": ["yyyy-MM-dd"],
    }

    valid, rejects, _ = prepare_silver(raw, config, "run-iam")

    assert "identity_master" in valid
    assert "iga_entitlements" in valid
    assert "iga_access_assignments" in valid
    assert "access_certifications" in valid
    assert valid["identity_master"].count() == 1
    assert valid["iga_access_assignments"].count() == 1
    assert sum(frame.count() for frame in rejects) == 0

    context = build_access_context(valid, date(2025, 2, 1))
    assert context.count() == 1
    row = context.first()
    assert row.identidade_id == "ID-CRE-0001"
    assert row.entitlement_id == "ENT-CRE-001"
    assert row.cross_community is False
    assert row.approval_exists is True
    assert row.account_count == 1
    assert row.certification_exists is True
    assert row.certification_decisao == "MAINTAIN"
    assert len(context.columns) == len(set(context.columns))
