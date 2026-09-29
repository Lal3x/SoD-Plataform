"""Approval Silver normalization."""

from pyspark.sql import DataFrame

from .transform import normalize_strings, parse_date


def transform(df: DataFrame, formats: list[str]) -> DataFrame:
    df = normalize_strings(df)
    for column in ("identidade_id", "entitlement_id"):
        df = df.withColumn(column, df[column].cast("string"))
    return parse_date(df, "data_aprovacao", formats)
