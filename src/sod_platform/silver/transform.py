"""Shared deterministic Silver normalization and validation helpers."""

from __future__ import annotations

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

LINEAGE = [
    "_ingestion_id",
    "_source_name",
    "_source_file",
    "_source_file_hash",
    "_ingestion_timestamp",
    "_ingestion_date",
]


def normalize_strings(df: DataFrame) -> DataFrame:
    if "_raw_data" not in df.columns:
        df = df.withColumn(
            "_raw_data",
            F.to_json(
                F.struct(*[F.col(c) for c in df.columns]), {"ignoreNullFields": "false"}
            ),
        )
    for column in ("comunidade", "comunidade_dona_sigla"):
        if column in df.columns and f"{column}_original" not in df.columns:
            df = df.withColumn(f"{column}_original", F.col(column))
    for field in df.schema.fields:
        if (
            not field.name.startswith("_")
            and field.dataType.simpleString() == "string"
            and not field.name.endswith("_original")
        ):
            df = df.withColumn(
                field.name,
                F.when(
                    F.trim(F.regexp_replace(F.col(field.name), r"\s+", " ")) == "", None
                ).otherwise(F.trim(F.regexp_replace(F.col(field.name), r"\s+", " "))),
            )
    if "comunidade" in df.columns:
        df = df.withColumn("comunidade", F.initcap(F.lower(F.trim("comunidade"))))
    if "comunidade_dona_sigla" in df.columns:
        df = df.withColumn(
            "comunidade_dona_sigla", F.initcap(F.lower(F.trim("comunidade_dona_sigla")))
        )
    return df


def parse_date(df: DataFrame, column: str, formats: list[str]) -> DataFrame:
    value = F.col(column).cast("string")
    parsed = None
    for fmt in formats:
        candidate = F.to_date(F.try_to_timestamp(value, F.lit(fmt)))
        parsed = candidate if parsed is None else F.coalesce(parsed, candidate)
    if f"{column}_original" not in df.columns:
        df = df.withColumn(f"{column}_original", value)
    return df.withColumn(column, parsed)


def duplicate_flags(df: DataFrame, business_columns: list[str]) -> DataFrame:
    """Keep deterministic first row for exact business duplicates, flag the rest."""
    stable_order = [
        c
        for c in (
            "_source_file_hash",
            "_source_file",
            "_ingestion_timestamp",
            "_ingestion_id",
        )
        if c in df.columns
    ]
    order_cols = [F.col(c).asc_nulls_first() for c in stable_order]
    if not order_cols:
        order_cols = [F.to_json(F.struct(*[F.col(c) for c in df.columns])).asc()]
    order_cols.append(F.to_json(F.struct(*[F.col(c) for c in df.columns])).asc())
    w = Window.partitionBy(*business_columns).orderBy(*order_cols)
    return df.withColumn("_duplicate_rank", F.row_number().over(w))
