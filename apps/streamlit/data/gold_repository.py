"""Read-only operational queries over the frozen Gold snapshot."""

from __future__ import annotations

import json
import os

from pyspark.sql import functions as F

from apps.streamlit.config import DATASET_VERSION, EVIDENCE_TABLE, GOLD_TABLE, ROOT
from apps.streamlit.data.base import ContractError, SparkSource
from apps.streamlit.data.cache import cached_gold_query

REQUIRED = {
    "grant_id",
    "assessment_date",
    "identidade_id",
    "entitlement_id",
    "sigla_id",
    "identity_community",
    "policy_decision",
    "policy_rule_id",
    "risk_score",
    "risk_band",
    "expected_access_state",
    "dataset_version",
}
FILTERS = {
    "identity_community",
    "squad",
    "cargo",
    "identity_type",
    "sigla_id",
    "entitlement_id",
    "policy_decision",
    "policy_rule_id",
    "risk_band",
    "expected_access_state",
    "selected_baseline_level",
    "privileged",
    "regulatory_scope",
    "sigla_publica",
    "birthright",
    "review_required",
    "remediation_candidate",
    "approval_evidence_status",
    "certification_status",
    "criticidade",
    "approval_match_strength",
}
SEARCH = {"grant_id", "identidade_id", "entitlement_id", "sigla_id"}


class GoldRepository:
    def __init__(self, source: SparkSource):
        self.source = source

    @staticmethod
    def snapshot_token():
        freeze = ROOT / "artifacts/freezes/v2-gold-runtime-freeze.json"
        metadata = json.loads(freeze.read_text())
        warehouse = os.getenv("SOD_WAREHOUSE", str(ROOT / "data/warehouse"))
        return f"{warehouse}:{metadata['output_snapshot']}"

    def frame(self):
        frame = self.source.table(GOLD_TABLE, REQUIRED)
        return frame.where(F.col("dataset_version") == DATASET_VERSION)

    @cached_gold_query()
    def get_executive_metrics(self):
        frame = self.frame()
        return (
            frame.agg(
                F.count("*").alias("total"),
                F.sum(F.col("review_required").cast("long")).alias("review"),
                F.sum(F.col("remediation_candidate").cast("long")).alias("remediation"),
                F.sum(F.col("privileged").cast("long")).alias("privileged"),
                F.sum(
                    (
                        F.col("regulatory_scope").isNotNull()
                        & (F.col("regulatory_scope") != "NONE")
                    ).cast("long")
                ).alias("regulatory"),
            )
            .first()
            .asDict()
        )

    @cached_gold_query()
    def distribution(self, column: str, filters: dict | None = None):
        if column not in self.frame().columns:
            raise ContractError(f"Coluna indisponível: {column}")
        frame = self._filtered(filters)
        return self.source.records(
            frame.groupBy(column).count().orderBy(F.desc("count")), 200
        )

    def get_policy_distribution(self):
        return self.distribution("policy_decision")

    def get_risk_distribution(self):
        return self.distribution("risk_band")

    @cached_gold_query()
    def get_policy_risk_matrix(self):
        return self.source.records(
            self.frame()
            .groupBy("policy_decision", "risk_band")
            .count()
            .orderBy("policy_decision", "risk_band"),
            100,
        )

    def _filtered(self, filters: dict | None = None, search: str = ""):
        frame = self.frame()
        for key, value in (filters or {}).items():
            if key not in FILTERS or key not in frame.columns:
                raise ContractError(f"Filtro indisponível: {key}")
            if value is not None and value != "":
                frame = frame.where(F.col(key) == F.lit(value))
        if search:
            term = search.strip().lower()
            frame = frame.where(
                F.lower(F.col("grant_id")).contains(term)
                | F.lower(F.col("identidade_id")).contains(term)
                | F.lower(F.col("entitlement_id")).contains(term)
                | F.lower(F.col("sigla_id")).contains(term)
            )
        return frame

    @cached_gold_query(ttl=120)
    def search_assessments(
        self,
        filters: dict | None = None,
        search: str = "",
        *,
        limit: int = 50,
        offset: int = 0,
        sort_risk: bool = False,
    ):
        if not 1 <= limit <= 500 or offset < 0 or offset > 100000:
            raise ValueError("Paginação fora dos limites")
        frame = self._filtered(filters, search)
        order = (
            [F.desc("risk_score"), F.asc("grant_id")]
            if sort_risk
            else [F.asc("grant_id")]
        )
        rows = self.source.records(
            frame.orderBy(*order).limit(offset + limit), offset + limit
        )
        return rows[offset:]

    @cached_gold_query(ttl=120)
    def count_assessments(self, filters: dict | None = None, search: str = ""):
        return self._filtered(filters, search).count()

    @cached_gold_query()
    def get_filter_options(self, fields: tuple[str, ...]):
        frame = self.frame()
        missing = set(fields) - (FILTERS & set(frame.columns))
        if missing:
            raise ContractError(f"Filtros indisponíveis: {', '.join(sorted(missing))}")
        row = frame.agg(
            *[
                F.sort_array(F.collect_set(F.col(field))).alias(field)
                for field in fields
            ]
        ).first()
        return {field: row[field] or [] for field in fields}

    def get_grant(self, grant_id: str):
        rows = self.source.records(self.frame().where(F.col("grant_id") == grant_id), 2)
        if len(rows) > 1:
            raise ContractError("Grant duplicado na Gold")
        return rows[0] if rows else None

    def get_grant_evidence(self, grant_id: str):
        frame = self.source.table(
            EVIDENCE_TABLE, {"grant_id", "evidence_id", "evidence_type"}
        )
        return self.source.records(
            frame.where(F.col("grant_id") == grant_id).orderBy(
                "evidence_type", "evidence_id"
            ),
            100,
        )

    def get_remediation_queue(self, filters: dict | None = None, **kwargs):
        return self.search_assessments(
            {**(filters or {}), "policy_decision": "INDEVIDO"}, sort_risk=True, **kwargs
        )

    def get_review_queue(self, filters: dict | None = None, **kwargs):
        return self.search_assessments(
            {**(filters or {}), "policy_decision": "REVISAO"}, sort_risk=True, **kwargs
        )

    @cached_gold_query()
    def group_analysis(
        self, dimension: str, limit: int = 30, sort_by: str = "total_grants"
    ):
        if dimension not in FILTERS or dimension not in self.frame().columns:
            raise ContractError(f"Dimensão indisponível: {dimension}")
        if sort_by not in {
            "total_grants",
            "indevido",
            "revisao",
            "risk_critical",
            "risk_high",
        }:
            raise ValueError("Ordenação indisponível")
        frame = (
            self.frame()
            .groupBy(dimension)
            .agg(
                F.count("*").alias("total_grants"),
                F.countDistinct("identidade_id").alias("unique_identities"),
                F.countDistinct("entitlement_id").alias("unique_entitlements"),
                *[
                    F.sum((F.col("policy_decision") == value).cast("long")).alias(
                        value.lower()
                    )
                    for value in ("PADRAO", "LEGITIMO", "INDEVIDO", "REVISAO")
                ],
                *[
                    F.sum((F.col("risk_band") == value).cast("long")).alias(
                        f"risk_{value.lower()}"
                    )
                    for value in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
                ],
                F.sum(F.col("privileged").cast("long")).alias("privileged"),
                F.sum(
                    (
                        F.col("regulatory_scope").isNotNull()
                        & (F.col("regulatory_scope") != "NONE")
                    ).cast("long")
                ).alias("regulatory"),
            )
        )
        frame = (
            frame.withColumn("review_rate", F.col("revisao") / F.col("total_grants"))
            .withColumn("indevido_rate", F.col("indevido") / F.col("total_grants"))
            .withColumn("privileged_rate", F.col("privileged") / F.col("total_grants"))
        )
        return self.source.records(
            frame.orderBy(F.desc(sort_by), F.asc(dimension)), limit
        )

    @cached_gold_query()
    def get_review_analysis(self, dimension: str, limit: int = 30):
        if dimension not in FILTERS or dimension not in self.frame().columns:
            raise ContractError(f"Dimensão indisponível: {dimension}")
        frame = (
            self.frame()
            .groupBy(dimension)
            .agg(
                F.count("*").alias("total_grants"),
                F.sum((F.col("policy_decision") == "REVISAO").cast("long")).alias(
                    "review_grants"
                ),
            )
            .withColumn("review_rate", F.col("review_grants") / F.col("total_grants"))
        )
        return self.source.records(
            frame.orderBy(F.desc("review_grants"), F.asc(dimension)), limit
        )

    def get_community_analysis(self, sort_by: str = "total_grants"):
        return self.group_analysis("identity_community", sort_by=sort_by)

    def get_application_analysis(self, sort_by: str = "total_grants"):
        return self.group_analysis("sigla_id", sort_by=sort_by)

    def get_entitlement_analysis(self):
        return self.group_analysis("entitlement_id")

    def get_expected_access_analysis(self, dimension: str = "expected_access_state"):
        return self.distribution(dimension)

    @cached_gold_query()
    def get_baseline_analysis(self):
        frame = (
            self.frame()
            .groupBy("selected_baseline_level")
            .agg(
                F.count("*").alias("grants"),
                F.avg("population_size").alias("mean_population_size"),
                F.avg("support_count").alias("mean_support_count"),
                F.avg("prevalence").alias("mean_prevalence"),
            )
        )
        return self.source.records(frame.orderBy(F.desc("grants")), 50)

    @cached_gold_query()
    def get_prevalence_distribution(self):
        frame = (
            self.frame()
            .where(F.col("prevalence").isNotNull())
            .withColumn(
                "prevalence_band",
                F.floor(F.col("prevalence") * 10) / 10,
            )
            .groupBy("prevalence_band")
            .count()
            .orderBy("prevalence_band")
        )
        return self.source.records(frame, 20)
