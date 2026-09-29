"""Complete descriptive, frozen-source metrics in the offline mart."""

from pathlib import Path

from sod_platform.bronze.ingestion.spark import create_spark_session

ROOT = Path(__file__).resolve().parents[1]


def main():
    spark = create_spark_session(ROOT, "sod-v2-validation-descriptive")
    try:
        bronze = "sod.bronze.access_assignments"
        raw_count = spark.table(bronze).count()
        hts_count = (
            spark.table("sod.access_intelligence.hard_trusted_set")
            .where("hard_trusted_flag")
            .count()
        )
        rows = [("V2", "RAW_ASSIGNMENTS", raw_count), ("V2", "HTS_ANCHORS", hts_count)]
        for row in (
            spark.table("sod.gold.sod_assessment_gold001")
            .groupBy("risk_band")
            .count()
            .collect()
        ):
            rows.append(("V2", "RISK_" + row["risk_band"], row["count"]))
        existing = {
            (row["dataset_version"], row["metric"])
            for row in spark.table("sod.validation.pipeline_evolution")
            .select("dataset_version", "metric")
            .collect()
        }
        additions = [row for row in rows if row[:2] not in existing]
        if additions:
            spark.createDataFrame(
                additions, ["dataset_version", "metric", "value"]
            ).writeTo("sod.validation.pipeline_evolution").append()
        comparison = "sod.validation.v1_v2_comparison"
        if "v1_rate" not in spark.table(comparison).columns:
            spark.sql(
                f"ALTER TABLE {comparison} ADD COLUMNS (v1_rate DOUBLE, v2_rate DOUBLE)"
            )
            spark.sql(
                f"UPDATE {comparison} SET v1_rate = v1_count / 68830.0, v2_rate = v2_count / 75577.0"
            )
        assert (
            spark.table("sod.validation.pipeline_evolution")
            .where("metric IN ('RISK_LOW','RISK_MEDIUM','RISK_HIGH','RISK_CRITICAL')")
            .agg({"value": "sum"})
            .first()[0]
            == 75577
        )
        print("V2 VALIDATION DESCRIPTIVE METRICS COMPLETE")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
