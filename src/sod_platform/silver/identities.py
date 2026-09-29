"""Identity Silver normalization."""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from .transform import normalize_strings, parse_date


def transform(df: DataFrame, formats: list[str]) -> DataFrame:
    df = normalize_strings(df)
    df = df.withColumn("identidade_id", df.identidade_id.cast("string"))
    df = df.withColumn("tipo_identidade", F.lower("tipo_identidade"))
    return parse_date(df, "data_entrada_comunidade_atual", formats)
