"""V2 canonical grant identity across duplicated source batches."""

from pyspark.sql import functions as F

from sod_platform.silver.accesses import transform
from sod_platform.silver.transform import duplicate_flags


def test_grant_id_is_stable_across_files_and_repartition(spark):
    rows = [
        (
            "ID-CRE-0001",
            "ENT-CRE-001",
            "2023-05-29",
            "atribuido",
            "2025-01-19",
            f"batch-{batch:05d}",
        )
        for batch in (1, 76)
    ]
    raw = spark.createDataFrame(
        rows,
        "identidade_id string, entitlement_id string, data_concessao string, "
        "tipo_atribuicao string, ultimo_uso string, _source_file string",
    )
    outputs = []
    for partitions in (1, 4):
        frame = transform(raw.repartition(partitions), ["yyyy-MM-dd"])
        ids = [row.grant_id for row in frame.select("grant_id").collect()]
        assert len(set(ids)) == 1
        assert frame.select("grant_id_generation_method").first()[0] == (
            "SHA256_IDENTITY_ENTITLEMENT_V2"
        )
        business = [
            name
            for name in frame.columns
            if not name.startswith("_") and not name.endswith("_original")
        ]
        ranked = duplicate_flags(frame, business)
        assert ranked.where(F.col("_duplicate_rank") == 1).count() == 1
        assert ranked.where(F.col("_duplicate_rank") == 2).count() == 1
        outputs.append(ids[0])
    assert outputs[0] == outputs[1]
