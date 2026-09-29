"""Build quarantine records without dropping source payload or lineage."""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def quarantine(
    df: DataFrame, table: str, code: str, message: str, rule: str, run_id: str
) -> DataFrame:
    from ..transform import LINEAGE

    lineage = [
        (
            F.col(c)
            if c in df.columns
            else F.lit(None).cast(
                "timestamp"
                if c == "_ingestion_timestamp"
                else "date"
                if c == "_ingestion_date"
                else "string"
            )
        ).alias(c)
        for c in LINEAGE
    ]
    if {"identidade_id", "entitlement_id"}.issubset(df.columns):
        key_expr = F.concat_ws("/", F.col("identidade_id"), F.col("entitlement_id"))
    elif "identidade_id" in df.columns:
        key_expr = F.col("identidade_id").cast("string")
    elif "entitlement_id" in df.columns:
        key_expr = F.col("entitlement_id").cast("string")
    else:
        key_expr = F.lit(None).cast("string")
    return df.select(
        F.lit(table).alias("source_table"),
        key_expr.alias("record_key"),
        *lineage,
        F.lit(code).alias("error_code"),
        F.lit(message).alias("error_message"),
        F.lit(rule).alias("validation_rule"),
        F.current_timestamp().alias("detected_at"),
        (
            F.col("_raw_data")
            if "_raw_data" in df.columns
            else F.to_json(F.struct(*[F.col(c) for c in df.columns]))
        ).alias("original_data"),
        F.lit(run_id).alias("_silver_run_id"),
    )
