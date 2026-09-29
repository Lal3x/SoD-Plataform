"""Factual context, without access decisions or invented source identifiers."""

from datetime import date

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

from sod_platform.silver.contract import INPUT_SCHEMAS, canonicalize_raw_tables
from sod_platform.silver.transform import LINEAGE

PAIR = ["identidade_id", "entitlement_id"]
GRANT = ["grant_id"]


def _project(frame, name, lineage_name=None):
    columns = [c for c in INPUT_SCHEMAS[name] if c in frame.columns]
    # These are Silver-derived, traceability facts for access assignments, not
    # source-contract fields.  Preserve them in Access Context so operational
    # metrics can distinguish source and deterministic technical grant keys.
    if name == "iga_access_assignments":
        columns.extend(
            c
            for c in ("grant_id", "grant_id_generated", "grant_id_generation_method")
            if c in frame.columns and c not in columns
        )
    lineage = [F.col(c) for c in LINEAGE if c in frame.columns]
    return frame.select(
        *columns,
        (
            F.to_json(F.struct(*lineage)) if lineage else F.lit(None).cast("string")
        ).alias(lineage_name or f"_{name}_lineage"),
    )


def build_access_context(
    tables: dict[str, DataFrame], reference_date: date
) -> DataFrame:
    tables = canonicalize_raw_tables(tables)
    access = _project(
        tables["iga_access_assignments"], "iga_access_assignments", "_accesses_lineage"
    )
    # The assignment source is a current snapshot and has no lifecycle fields.
    active = access.where(F.col("data_concessao") <= F.lit(reference_date))
    frame = active.join(
        _project(tables["identity_master"], "identity_master"), "identidade_id"
    ).join(_project(tables["iga_entitlements"], "iga_entitlements"), "entitlement_id")
    requests = tables.get("iga_access_requests")
    if requests is not None:
        approval = _project(requests, "iga_access_requests", "_approvals_lineage")
        if "status_solicitacao" in approval.columns:
            approval = approval.where(F.col("status_solicitacao") == "APPROVED")
        approval = approval.where(
            F.col("data_aprovacao").isNotNull()
            & F.col("aprovador").isNotNull()
            & (F.col("data_aprovacao") <= F.lit(reference_date))
        )
        candidates = active.join(approval, PAIR, "inner")
        candidates = candidates.where(
            F.col("data_aprovacao") <= F.col("data_concessao")
        )
        candidate_window = Window.partitionBy(*GRANT)
        candidates = candidates.withColumn(
            "_approval_candidate_count", F.count(F.lit(1)).over(candidate_window)
        ).withColumn("_approval_relevance", F.lit("UNCERTAIN"))
        chosen = candidates.withColumn(
            "_rank",
            F.row_number().over(
                Window.partitionBy(*GRANT).orderBy(
                    F.col("data_aprovacao").desc(),
                    F.col("aprovador").asc(),
                    F.to_json(F.struct(*[F.col(c) for c in candidates.columns])).asc(),
                )
            ),
        )
        chosen = chosen.where("_rank = 1").select(
            *GRANT,
            *[c for c in approval.columns if c not in PAIR],
            "_approval_relevance",
            F.when(
                F.col("_approval_candidate_count") == 1,
                F.lit("STRONG_INFERRED"),
            )
            .otherwise(F.lit("AMBIGUOUS"))
            .alias("approval_linkage_quality"),
        )
        frame = frame.join(chosen, GRANT, "left")
    else:
        frame = (
            frame.withColumn("data_aprovacao", F.lit(None).cast("date"))
            .withColumn("aprovador", F.lit(None).cast("string"))
            .withColumn("_approval_relevance", F.lit(None).cast("string"))
            .withColumn("approval_linkage_quality", F.lit(None).cast("string"))
        )
    if "application_catalog" in tables:
        catalog = _project(tables["application_catalog"], "application_catalog")
        catalog = catalog.select(
            "sigla_id",
            *[
                F.col(c).alias(f"catalog_{c}")
                for c in catalog.columns
                if c != "sigla_id"
            ],
        )
        frame = frame.join(catalog, "sigla_id", "left")
    if "identity_directory" in tables:
        directory = _project(tables["identity_directory"], "identity_directory")
        accounts = directory.groupBy("identidade_id").agg(
            F.sort_array(
                F.collect_list(
                    F.struct(*[c for c in directory.columns if c != "identidade_id"])
                )
            ).alias("accounts"),
            F.count("account_id").alias("account_count"),
            F.max("ultima_autenticacao").alias("account_last_authentication"),
            F.sort_array(F.collect_set("status_conta")).alias("account_statuses"),
        )
        frame = frame.join(accounts, "identidade_id", "left").fillna(
            {"account_count": 0}
        )
    if "access_certifications" in tables:
        cert = _project(tables["access_certifications"], "access_certifications")
        pending = cert.where(
            (F.col("decisao") == "PENDING")
            & (
                F.col("data_revisao").isNull()
                | (F.col("data_revisao") <= F.lit(reference_date))
            )
        )
        pending = pending.groupBy(*PAIR).agg(
            F.count("*").alias("certification_pending_count")
        )
        frame = frame.join(pending, PAIR, "left").fillna(
            {"certification_pending_count": 0}
        )
        cert = cert.where(F.col("data_revisao") <= F.lit(reference_date))
        cert = (
            cert.withColumn(
                "_rank",
                F.row_number().over(
                    Window.partitionBy(*PAIR).orderBy(
                        F.col("data_revisao").desc(),
                        F.col("campaign_id").asc(),
                        F.to_json(F.struct(*cert.columns)).asc(),
                    )
                ),
            )
            .where("_rank = 1")
            .drop("_rank")
        )
        cert = cert.select(
            *PAIR,
            *[
                F.col(c).alias(f"certification_{c}")
                for c in cert.columns
                if c not in PAIR
            ],
        )
        frame = frame.join(cert, PAIR, "left").withColumn(
            "certification_exists", F.col("certification_data_revisao").isNotNull()
        )
    return (
        frame.withColumn("reference_date", F.lit(reference_date))
        .withColumn("assessment_date", F.lit(reference_date))
        .withColumn(
            "cross_community", F.col("comunidade") != F.col("comunidade_dona_sigla")
        )
        .withColumn("approval_exists", F.col("data_aprovacao").isNotNull())
        .withColumn(
            "approval_relevance",
            F.coalesce(F.col("_approval_relevance"), F.lit("NOT_FOUND")),
        )
        .withColumn(
            "approval_linkage_quality",
            F.coalesce(F.col("approval_linkage_quality"), F.lit("UNKNOWN")),
        )
        .withColumn(
            "approval_to_grant_delta_days",
            F.when(
                F.col("approval_relevance") == "UNCERTAIN",
                F.datediff("data_concessao", "data_aprovacao"),
            ).cast("integer"),
        )
        .withColumn(
            "inherited_access",
            F.col("data_concessao") < F.col("data_entrada_comunidade_atual"),
        )
        .withColumn("never_used", F.col("ultimo_uso").isNull())
        .withColumn("inherited_access_candidate", F.col("inherited_access"))
        .withColumn("no_usage_recorded", F.col("never_used"))
        .withColumn("usage_coverage", F.lit("UNKNOWN"))
        .withColumn("identity_history_complete", F.lit(False))
        .withColumn("application_criticality", F.col("criticidade"))
        .withColumn("entitlement_privileged", F.col("privileged"))
        .withColumn("data_quality_blocking", F.lit(False))
        .withColumn(
            "source_snapshot_id",
            F.sha2(
                F.concat_ws(
                    "|",
                    *[
                        F.coalesce(F.col(c), F.lit(""))
                        for c in (
                            "_accesses_lineage",
                            "_identity_master_lineage",
                            "_iga_entitlements_lineage",
                        )
                        if c in frame.columns
                    ],
                ),
                256,
            ),
        )
        .withColumn("access_age_days", F.datediff("reference_date", "data_concessao"))
        .withColumn("days_since_last_use", F.datediff("reference_date", "ultimo_uso"))
    )
