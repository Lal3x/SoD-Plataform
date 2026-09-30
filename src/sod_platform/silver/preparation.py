"""Row policies independent of storage and Great Expectations diagnostics."""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from . import accesses, approvals, entitlements, identities
from .contract import (
    INPUT_SCHEMAS,
    TABLE_ALIASES,
    canonicalize_raw_tables,
    check_inputs,
)
from .quality.quarantine import quarantine
from .transform import LINEAGE, duplicate_flags, normalize_strings, parse_date


def _catalog_transform(df: DataFrame) -> DataFrame:
    df = normalize_strings(df)
    for column in (
        "sigla_id",
        "nome_sistema",
        "owner",
        "comunidade",
        "criticidade",
        "classificacao_dado",
        "regulatory_scope",
    ):
        if column in df.columns:
            df = df.withColumn(column, F.col(column).cast("string"))
    if "privileged" in df.columns:
        value = F.lower(F.trim(F.col("privileged").cast("string")))
        df = df.withColumn(
            "privileged",
            F.when(value.isin("true", "1", "yes", "sim"), True)
            .when(value.isin("false", "0", "no", "nao", "não"), False)
            .otherwise(None)
            .cast("boolean"),
        )
    return df


def _directory_transform(df: DataFrame, formats: list[str]) -> DataFrame:
    df = normalize_strings(df)
    for column in ("account_id", "identidade_id", "status_conta", "tipo_conta"):
        if column in df.columns:
            df = df.withColumn(column, F.col(column).cast("string"))
    for column in ("data_criacao", "ultima_autenticacao", "data_bloqueio"):
        if column in df.columns:
            df = parse_date(df, column, formats)
    return df


def _certification_transform(df: DataFrame, formats: list[str]) -> DataFrame:
    df = normalize_strings(df)
    for column in (
        "campaign_id",
        "identidade_id",
        "entitlement_id",
        "revisor",
        "decisao",
        "justificativa",
    ):
        if column in df.columns:
            df = df.withColumn(column, F.col(column).cast("string"))
    if "data_revisao" in df.columns:
        df = parse_date(df, "data_revisao", formats)
    return df


def _source_name_for(inputs: dict, name: str) -> str:
    if name in inputs:
        return inputs[name]
    for source_name, canonical_name in TABLE_ALIASES.items():
        if canonical_name == name and source_name in inputs:
            return inputs[source_name]
    return name


def prepare_silver(raw: dict[str, DataFrame], config: dict, run_id: str, cached=None):
    input_names = set(raw)
    check_inputs(raw)
    raw = canonicalize_raw_tables(raw)
    formats = config.get("date_formats", ["yyyy-MM-dd"])
    domains = config.get("domains", {})
    inputs = config.get("tables", {})

    transformed: dict[str, DataFrame] = {}
    for name, frame in raw.items():
        if name == "identity_master":
            transformed[name] = identities.transform(frame, formats)
        elif name == "identity_directory":
            transformed[name] = _directory_transform(frame, formats)
        elif name == "iga_entitlements":
            transformed[name] = entitlements.transform(frame)
        elif name == "application_catalog":
            transformed[name] = _catalog_transform(frame)
        elif name == "iga_access_assignments":
            transformed[name] = accesses.transform(frame, formats)
        elif name == "iga_access_requests":
            transformed[name] = approvals.transform(frame, formats)
        elif name == "access_certifications":
            transformed[name] = _certification_transform(frame, formats)
        elif name == "identities":
            transformed[name] = identities.transform(frame, formats)
        elif name == "entitlements":
            transformed[name] = entitlements.transform(frame)
        elif name == "accesses":
            transformed[name] = accesses.transform(frame, formats)
        elif name == "approvals":
            transformed[name] = approvals.transform(frame, formats)

    rejects: list[DataFrame] = []
    valid: dict[str, DataFrame] = {}

    def split(
        name: str,
        df: DataFrame,
        condition: F.Column,
        code: str,
        message: str,
        rule: str,
    ) -> DataFrame:
        bad = df.where(condition)
        rejects.append(
            quarantine(bad, _source_name_for(inputs, name), code, message, rule, run_id)
        )
        return df.where(~condition)

    for name, df in transformed.items():
        if df is None:
            continue
        # Apply the complete declared type contract, including optional temporal fields.
        for column, dtype in INPUT_SCHEMAS[name].items():
            if column not in df.columns:
                continue
            if dtype == "date" and f"{column}_original" not in df.columns:
                df = parse_date(df, column, formats)
            elif dtype == "boolean":
                if f"{column}_original" not in df.columns:
                    df = df.withColumn(
                        f"{column}_original", F.col(column).cast("string")
                    )
                value = F.lower(F.col(column).cast("string"))
                df = df.withColumn(
                    column,
                    F.when(value.isin("true", "1", "yes", "sim"), True)
                    .when(value.isin("false", "0", "no", "nao", "não"), False)
                    .cast("boolean"),
                )
            elif dtype == "string":
                df = df.withColumn(column, F.col(column).cast("string"))
        if name in {"identity_master", "identities"}:
            required = ["identidade_id", "comunidade", "tipo_identidade"]
            date_columns = ["data_entrada_comunidade_atual"]
            domain_column = "tipo_identidade"
            boolean_columns = ()
        elif name in {"iga_entitlements", "entitlements"}:
            required = ["entitlement_id", "sigla_id", "comunidade_dona_sigla"]
            date_columns = []
            domain_column = None
            boolean_columns = ("birthright", "sigla_publica")
        elif name in {"iga_access_assignments", "accesses"}:
            required = [
                "identidade_id",
                "entitlement_id",
                "data_concessao",
                "tipo_atribuicao",
            ]
            date_columns = ["data_concessao", "ultimo_uso"]
            domain_column = "tipo_atribuicao"
            boolean_columns = ()
        elif name in {"iga_access_requests", "approvals"}:
            required = ["identidade_id", "entitlement_id"]
            if "status_solicitacao" in df.columns:
                required += [
                    "request_id",
                    "solicitante",
                    "data_solicitacao",
                    "status_solicitacao",
                ]
            else:
                required += ["data_aprovacao", "aprovador"]
            date_columns = ["data_aprovacao"]
            domain_column = None
            boolean_columns = ()
        elif name == "application_catalog":
            required = ["sigla_id", "nome_sistema", "comunidade"]
            date_columns = []
            domain_column = None
            boolean_columns = ()
        elif name == "identity_directory":
            required = ["account_id", "status_conta", "tipo_conta"]
            date_columns = ["data_criacao", "ultima_autenticacao", "data_bloqueio"]
            domain_column = None
            boolean_columns = ()
        elif name == "access_certifications":
            required = [
                "campaign_id",
                "identidade_id",
                "entitlement_id",
                "decisao",
            ]
            date_columns = ["data_revisao"]
            domain_column = None
            boolean_columns = ()
        else:
            continue

        date_columns = [
            c for c, t in INPUT_SCHEMAS[name].items() if t == "date" and c in df.columns
        ]
        boolean_columns = [
            c
            for c, t in INPUT_SCHEMAS[name].items()
            if t == "boolean" and c in df.columns
        ]
        if cached is not None:
            df = df.cache()
            cached.append(df)
        transformed[name] = df

        missing = F.lit(False)
        for column in required:
            if (
                column in {"data_concessao", "data_aprovacao", "data_revisao"}
                and column in df.columns
            ):
                missing = missing | (
                    F.col(column).isNull() & F.col(f"{column}_original").isNull()
                )
            elif column in df.columns:
                missing = missing | F.col(column).isNull()
        df = split(
            name,
            df,
            missing,
            "MISSING_REQUIRED_FIELD",
            "Campo obrigatório ausente ou inválido",
            "required_fields",
        )

        if name == "identity_directory":
            df = split(
                name,
                df,
                (F.col("tipo_conta") != "service") & F.col("identidade_id").isNull(),
                "MISSING_REQUIRED_FIELD",
                "Conta humana sem identidade",
                "human_account_identity",
            )

        if "status_solicitacao" in df.columns:
            df = split(
                name,
                df,
                (F.col("status_solicitacao") == "APPROVED")
                & (F.col("data_aprovacao").isNull() | F.col("aprovador").isNull()),
                "MISSING_APPROVAL_EVIDENCE",
                "Solicitação aprovada sem evidência obrigatória",
                "approved_evidence",
            )

        if name == "access_certifications":
            df = split(
                name,
                df,
                (F.col("decisao") != "PENDING")
                & (F.col("data_revisao").isNull() | F.col("revisor").isNull()),
                "MISSING_CERTIFICATION_EVIDENCE",
                "Revisão concluída sem data ou revisor",
                "completed_review",
            )

        for column in date_columns:
            if column not in df.columns:
                continue
            original = f"{column}_original"
            invalid = F.col(column).isNull() & F.col(original).isNotNull()
            df = split(
                name,
                df,
                invalid,
                "INVALID_DATE",
                f"Data inválida em {column}",
                f"parse_{column}",
            )

        if domain_column and domain_column in domains:
            allowed = domains[domain_column]
            df = split(
                name,
                df,
                ~F.col(domain_column).isin(allowed),
                "INVALID_DOMAIN",
                f"Valor fora do domínio de {domain_column}",
                f"domain_{domain_column}",
            )

        for column, allowed in domains.items():
            if column in df.columns and column != domain_column:
                df = split(
                    name,
                    df,
                    F.col(column).isNotNull() & ~F.col(column).isin(allowed),
                    "INVALID_DOMAIN",
                    f"Valor fora do domínio de {column}",
                    f"domain_{column}",
                )
        for earlier, later in (
            ("data_concessao", "ultimo_uso"),
            ("data_concessao", "data_revogacao"),
            ("data_solicitacao", "data_aprovacao"),
            ("data_criacao", "ultima_autenticacao"),
            ("data_criacao", "data_bloqueio"),
        ):
            if earlier in df.columns and later in df.columns:
                df = split(
                    name,
                    df,
                    F.coalesce(F.col(later) < F.col(earlier), F.lit(False)),
                    "INVALID_TEMPORAL_ORDER",
                    f"{later} anterior a {earlier}",
                    f"order_{earlier}_{later}",
                )

        for column in boolean_columns:
            if column not in df.columns:
                continue
            df = split(
                name,
                df,
                F.col(column).isNull(),
                "INVALID_BOOLEAN",
                f"Booleano inválido em {column}",
                f"boolean_{column}",
            )

        business = [
            c
            for c in df.columns
            if c not in LINEAGE
            and not c.startswith("_")
            and not c.endswith("_original")
        ]
        ranked = duplicate_flags(df, business)
        duplicate = ranked.where(F.col("_duplicate_rank") > 1).drop("_duplicate_rank")
        if duplicate.limit(1).count():
            rejects.append(
                quarantine(
                    duplicate,
                    _source_name_for(inputs, name),
                    "DUPLICATE_RECORD",
                    "Duplicata exata; uma ocorrência mantida",
                    "exact_business_row",
                    run_id,
                )
            )
        df = ranked.where(F.col("_duplicate_rank") == 1).drop("_duplicate_rank")

        unique_key = {
            "identity_master": ["identidade_id"],
            "identities": ["identidade_id"],
            "iga_entitlements": ["entitlement_id"],
            "entitlements": ["entitlement_id"],
            "iga_access_assignments": ["grant_id"],
            "accesses": ["identidade_id", "entitlement_id"],
            "identity_directory": ["account_id"],
            "application_catalog": ["sigla_id"],
            "iga_access_requests": ["request_id"],
            "approvals": ["request_id"],
            "access_certifications": [
                "campaign_id",
                "identidade_id",
                "entitlement_id",
            ],
        }.get(name)
        if unique_key and all(col in df.columns for col in unique_key):
            counts = (
                df.groupBy(*unique_key).count().where("count > 1").select(*unique_key)
            )
            conflicts = df.join(counts, unique_key, "inner")
            if conflicts.limit(1).count():
                rejects.append(
                    quarantine(
                        conflicts,
                        _source_name_for(inputs, name),
                        "DUPLICATE_KEY_CONFLICT",
                        f"Chave {unique_key} possui payloads conflitantes",
                        f"unique_{unique_key}",
                        run_id,
                    )
                )
                df = df.join(counts, unique_key, "left_anti")
        if cached is not None:
            df = df.cache()
            cached.append(df)
        valid[name] = df

    identity_ids = valid.get("identity_master", valid.get("identities"))
    entitlement_ids = valid.get("iga_entitlements", valid.get("entitlements"))
    if identity_ids is not None and entitlement_ids is not None:
        for name in [
            "iga_access_assignments",
            "iga_access_requests",
            "access_certifications",
            "identity_directory",
        ]:
            df = valid.get(name)
            if df is None:
                continue
            id_key = identity_ids.select("identidade_id").distinct()
            ent_key = entitlement_ids.select("entitlement_id").distinct()
            orphan_identities = df.join(id_key, "identidade_id", "left_anti")
            unlinked_service = None
            if name == "identity_directory":
                service_without_identity = (F.col("tipo_conta") == "service") & F.col(
                    "identidade_id"
                ).isNull()
                unlinked_service = df.where(service_without_identity)
                orphan_identities = orphan_identities.where(~service_without_identity)
            if orphan_identities.limit(1).count():
                rejects.append(
                    quarantine(
                        orphan_identities,
                        _source_name_for(inputs, name),
                        "INVALID_IDENTITY_REFERENCE",
                        "Identidade não encontrada na Silver",
                        "identity_foreign_key",
                        run_id,
                    )
                )
            df = df.join(id_key, "identidade_id", "left_semi")
            if unlinked_service is not None:
                df = df.unionByName(unlinked_service)
            if "entitlement_id" not in df.columns:
                valid[name] = df
                continue
            orphan_entitlements = df.join(ent_key, "entitlement_id", "left_anti")
            if orphan_entitlements.limit(1).count():
                rejects.append(
                    quarantine(
                        orphan_entitlements,
                        _source_name_for(inputs, name),
                        "INVALID_ENTITLEMENT_REFERENCE",
                        "Entitlement não encontrada na Silver",
                        "entitlement_foreign_key",
                        run_id,
                    )
                )
            df = df.join(ent_key, "entitlement_id", "left_semi")
            valid[name] = df

    if "application_catalog" in valid and "iga_entitlements" in valid:
        catalog = valid["application_catalog"]
        ent = valid["iga_entitlements"]
        keys = catalog.select("sigla_id")
        rejects.append(
            quarantine(
                ent.join(keys, "sigla_id", "left_anti"),
                _source_name_for(inputs, "iga_entitlements"),
                "INVALID_APPLICATION_REFERENCE",
                "Aplicação não encontrada",
                "application_fk",
                run_id,
            )
        )
        # Keep authoritative catalog metadata separate; contradictions are DQ, not silently overwritten.
        joined = ent.join(
            catalog.select(
                "sigla_id",
                *[
                    F.col(c).alias(f"_catalog_{c}")
                    for c in (
                        "criticidade",
                        "classificacao_dado",
                        "privileged",
                        "regulatory_scope",
                    )
                ],
            ),
            "sigla_id",
            "inner",
        )
        conflict = F.lit(False)
        for c in (
            "criticidade",
            "classificacao_dado",
            "privileged",
            "regulatory_scope",
        ):
            if c in ent.columns:
                conflict = conflict | ~F.col(c).eqNullSafe(F.col(f"_catalog_{c}"))
        rejects.append(
            quarantine(
                joined.where(conflict).select(*ent.columns),
                _source_name_for(inputs, "iga_entitlements"),
                "APPLICATION_METADATA_CONFLICT",
                "Metadata diverge do catálogo",
                "catalog_consistency",
                run_id,
            )
        )
        valid["iga_entitlements"] = joined.where(~conflict).select(*ent.columns)
        # Propagate catalog rejection to dependent facts.
        for name in (
            "iga_access_assignments",
            "iga_access_requests",
            "access_certifications",
        ):
            if name in valid:
                df = valid[name]
                keys = valid["iga_entitlements"].select("entitlement_id")
                rejects.append(
                    quarantine(
                        df.join(keys, "entitlement_id", "left_anti"),
                        _source_name_for(inputs, name),
                        "INVALID_ENTITLEMENT_REFERENCE",
                        "Entitlement rejeitado pelo catálogo",
                        "catalog_entitlement_fk",
                        run_id,
                    )
                )
                valid[name] = df.join(keys, "entitlement_id", "left_semi")

    for alias, canonical in {
        "identities": "identity_master",
        "entitlements": "iga_entitlements",
        "accesses": "iga_access_assignments",
        "approvals": "iga_access_requests",
    }.items():
        if canonical in valid and alias in input_names:
            valid_frame = valid[canonical]
            transformed_frame = transformed[canonical]
            valid.pop(canonical, None)
            transformed.pop(canonical, None)
            valid[alias] = valid_frame
            transformed[alias] = transformed_frame

    return valid, rejects, transformed
