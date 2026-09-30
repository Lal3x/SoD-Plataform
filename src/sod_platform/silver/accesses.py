"""Access Silver normalization."""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from .transform import normalize_strings, parse_date


def transform(df: DataFrame, formats: list[str]) -> DataFrame:
    df = normalize_strings(df)
    for column in ("identidade_id", "entitlement_id"):
        if column not in df.columns:
            continue
        df = df.withColumn(column, F.col(column).cast("string"))
    for column in ("data_concessao", "ultimo_uso"):
        if column in df.columns:
            df = parse_date(df, column, formats)
    df = df.withColumn("tipo_atribuicao", F.lower("tipo_atribuicao"))
    # The physical source has no grant identifier. Silver always creates the
    # deterministic technical key and keeps its origin explicit.
    # The current snapshot contract has one canonical assignment per pair.
    # Length prefixes prevent separator ambiguity; source lineage stays in
    # separate columns and does not make duplicate batches distinct grants.
    key_columns = [
        F.concat(F.length(F.col(c)).cast("string"), F.lit(":"), F.col(c))
        for c in ("identidade_id", "entitlement_id")
    ]
    return (
        df.withColumn("grant_id_generated", F.lit(True))
        .withColumn(
            "grant_id",
            F.concat(F.lit("technical-"), F.sha2(F.concat_ws("|", *key_columns), 256)),
        )
        .withColumn(
            "grant_id_generation_method",
            F.lit("SHA256_IDENTITY_ENTITLEMENT_V2"),
        )
    )
