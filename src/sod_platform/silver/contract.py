"""Explicit source and output business schemas; missing columns fail the run."""

from __future__ import annotations

from pyspark.sql import DataFrame

INPUT_SCHEMAS = {
    "identity_master": {
        "identidade_id": "string",
        "comunidade": "string",
        "squad": "string",
        "cargo": "string",
        "tipo_identidade": "string",
        "gestor": "string",
        "data_entrada_comunidade_atual": "date",
        "status_identidade": "string",
        "data_desligamento": "date",
    },
    "identity_directory": {
        "account_id": "string",
        "identidade_id": "string",
        "status_conta": "string",
        "tipo_conta": "string",
        "data_criacao": "date",
        "ultima_autenticacao": "date",
        "data_bloqueio": "date",
    },
    "iga_entitlements": {
        "entitlement_id": "string",
        "sigla_id": "string",
        "comunidade_dona_sigla": "string",
        "birthright": "boolean",
        "sigla_publica": "boolean",
        "application_owner": "string",
        "criticidade": "string",
        "classificacao_dado": "string",
        "privileged": "boolean",
        "regulatory_scope": "string",
    },
    "application_catalog": {
        "sigla_id": "string",
        "nome_sistema": "string",
        "owner": "string",
        "comunidade": "string",
        "criticidade": "string",
        "classificacao_dado": "string",
        "privileged": "boolean",
        "regulatory_scope": "string",
    },
    "iga_access_assignments": {
        "identidade_id": "string",
        "entitlement_id": "string",
        "data_concessao": "date",
        "tipo_atribuicao": "string",
        "ultimo_uso": "date",
    },
    "iga_access_requests": {
        "request_id": "string",
        "identidade_id": "string",
        "entitlement_id": "string",
        "solicitante": "string",
        "data_solicitacao": "date",
        "status_solicitacao": "string",
        "aprovador": "string",
        "data_aprovacao": "date",
        "motivo": "string",
    },
    "access_certifications": {
        "campaign_id": "string",
        "identidade_id": "string",
        "entitlement_id": "string",
        "data_revisao": "date",
        "revisor": "string",
        "decisao": "string",
        "justificativa": "string",
    },
}

TABLE_ALIASES = {
    "identities": "identity_master",
    "entitlements": "iga_entitlements",
    "accesses": "iga_access_assignments",
    "approvals": "iga_access_requests",
    "identity_master": "identity_master",
    "identity_directory": "identity_directory",
    "iga_entitlements": "iga_entitlements",
    "application_catalog": "application_catalog",
    "iga_access_assignments": "iga_access_assignments",
    "iga_access_requests": "iga_access_requests",
    "access_certifications": "access_certifications",
}

LEGACY_INPUT_SCHEMAS = {
    "identities": {
        "identidade_id": "string",
        "comunidade": "string",
        "squad": "string",
        "cargo": "string",
        "tipo_identidade": "string",
        "gestor": "string",
        "data_entrada_comunidade_atual": "string",
    },
    "entitlements": {
        "entitlement_id": "string",
        "sigla_id": "string",
        "comunidade_dona_sigla": "string",
        "birthright": "string",
        "sigla_publica": "string",
    },
    "accesses": {
        "identidade_id": "string",
        "entitlement_id": "string",
        "data_concessao": "string",
        "tipo_atribuicao": "string",
        "ultimo_uso": "string",
    },
    "approvals": {
        "identidade_id": "string",
        "entitlement_id": "string",
        "data_aprovacao": "string",
        "aprovador": "string",
    },
}

SCHEMAS = {
    **INPUT_SCHEMAS,
    **LEGACY_INPUT_SCHEMAS,
}

OPTIONAL_COLUMNS: dict[str, set[str]] = {}


def canonicalize_raw_tables(raw: dict[str, DataFrame]) -> dict[str, DataFrame]:
    resolved: dict[str, DataFrame] = {}
    for name, frame in raw.items():
        key = TABLE_ALIASES.get(name, name)
        if key in resolved:
            raise ValueError(f"Multiple inputs resolve to {key}")
        resolved[key] = frame
    return resolved


def check_inputs(raw: dict[str, DataFrame]) -> None:
    for source_name, frame in raw.items():
        name = TABLE_ALIASES.get(source_name, source_name)
        columns = LEGACY_INPUT_SCHEMAS.get(source_name, INPUT_SCHEMAS.get(name))
        if columns is None:
            continue
        missing = set(columns) - OPTIONAL_COLUMNS.get(name, set()) - set(frame.columns)
        if missing:
            raise ValueError(f"Missing columns in {source_name}: {sorted(missing)}")
        for column in columns:
            if column not in frame.columns:
                continue
            dtype = frame.schema[column].dataType.simpleString()
            if dtype.startswith(("array", "map", "struct", "binary")):
                raise ValueError(
                    f"Unsupported source type: {source_name}.{column} {dtype}"
                )
