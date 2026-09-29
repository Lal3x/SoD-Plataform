"""Entitlement Silver normalization."""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from .transform import normalize_strings


def transform(df: DataFrame) -> DataFrame:
    df = normalize_strings(df)
    for column in ("entitlement_id", "sigla_id"):
        df = df.withColumn(column, F.col(column).cast("string"))
    for column in ("birthright", "sigla_publica"):
        value = F.lower(F.trim(F.col(column).cast("string")))
        df = df.withColumn(
            column,
            F.when(value.isin("true", "1", "yes", "sim"), True)
            .when(value.isin("false", "0", "no", "nao", "não"), False)
            .otherwise(None)
            .cast("boolean"),
        )
    return df
