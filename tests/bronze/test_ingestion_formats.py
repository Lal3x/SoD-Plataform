import json
from pathlib import Path

from openpyxl import Workbook

from sod_platform.bronze.ingestion.readers import read_source


def test_reads_supported_formats(spark, tmp_path: Path) -> None:
    csv_path = tmp_path / "input.csv"
    csv_path.write_text("id,name\n1,Ana\n", encoding="utf-8")
    json_path = tmp_path / "input.json"
    json_path.write_text(json.dumps([{"id": 1, "name": "Ana"}]), encoding="utf-8")
    parquet_path = tmp_path / "input.parquet"
    spark.createDataFrame([(1, "Ana")], ["id", "name"]).write.parquet(str(parquet_path))
    xlsx_path = tmp_path / "input.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["id", "name"])
    sheet.append([1, "Ana"])
    workbook.save(xlsx_path)

    for path, file_format, options in [
        (csv_path, "csv", {"header": "true"}),
        (json_path, "json", {"multiLine": "true", "primitivesAsString": "true"}),
        (parquet_path, "parquet", {}),
        (xlsx_path, "xlsx", {"sheet": "0"}),
    ]:
        frame = read_source(spark, path, file_format, options)
        assert frame.count() == 1
        assert frame.columns == ["id", "name"]
