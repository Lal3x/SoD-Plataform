"""Build Spark with an Iceberg Hadoop catalog for local or object storage."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from pyspark.sql import SparkSession

from sod_platform.common.env import load_project_env

SPARK_VERSION = "4.1"
SCALA_BINARY_VERSION = "2.13"


class SparkPrerequisiteError(RuntimeError):
    """Raised when the local machine cannot start the configured Spark runtime."""


def validate_java_runtime() -> None:
    """Require a supported local Java runtime before launching PySpark."""
    java_home = os.getenv("JAVA_HOME")
    java_executable = Path(java_home) / "bin" / "java" if java_home else None
    java_command = (
        str(java_executable)
        if java_executable and java_executable.is_file()
        else shutil.which("java")
    )
    if java_command is None:
        raise SparkPrerequisiteError(
            "PySpark 4.1.3 requires Java 17 or 21. Install a JRE/JDK and set JAVA_HOME, "
            "or make java available on PATH."
        )
    try:
        version_result = subprocess.run(
            [java_command, "-version"], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SparkPrerequisiteError(
            f"Unable to run Java executable {java_command}: {exc}"
        ) from exc
    version_text = version_result.stdout + version_result.stderr
    match = re.search(r'(?:version ")?(\d+)(?:[.\-"\s])', version_text)
    if match is None or int(match.group(1)) not in {17, 21}:
        detected = match.group(1) if match else "unknown"
        raise SparkPrerequisiteError(
            f"Spark 4.1.3 supports Java 17 or 21; found Java {detected} at {java_command}."
        )


def create_spark_session(
    project_root: Path, app_name: str = "sod-platform-bronze"
) -> SparkSession:
    """Create a local Spark session with Iceberg's Spark 4.1 runtime."""
    load_project_env(project_root)
    validate_java_runtime()
    iceberg_version = os.getenv("ICEBERG_VERSION", "1.11.0")
    warehouse_setting = os.getenv("SOD_WAREHOUSE")
    if warehouse_setting and "://" in warehouse_setting:
        warehouse_uri = warehouse_setting
    else:
        warehouse = Path(warehouse_setting or project_root / "data" / "warehouse")
        if not warehouse.is_absolute():
            warehouse = project_root / warehouse
        warehouse = warehouse.resolve()
        warehouse.mkdir(parents=True, exist_ok=True)
        warehouse_uri = warehouse.as_uri()
    package = (
        f"org.apache.iceberg:iceberg-spark-runtime-{SPARK_VERSION}_"
        f"{SCALA_BINARY_VERSION}:{iceberg_version}"
    )
    builder = (
        SparkSession.builder.appName(app_name)
        .master(os.getenv("SPARK_MASTER", "local[*]"))
        .config("spark.jars.packages", package)
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        )
        .config("spark.sql.catalog.sod", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.sod.type", "hadoop")
        .config("spark.sql.catalog.sod.warehouse", warehouse_uri)
        .config("spark.sql.defaultCatalog", "sod")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.storeAssignmentPolicy", "ANSI")
        .config(
            "spark.sql.shuffle.partitions", os.getenv("SPARK_SHUFFLE_PARTITIONS", "4")
        )
    )
    raw_overrides = os.getenv("SOD_SPARK_CONF_JSON", "{}")
    try:
        overrides = json.loads(raw_overrides)
    except json.JSONDecodeError as exc:
        raise ValueError("SOD_SPARK_CONF_JSON must contain a JSON object") from exc
    if not isinstance(overrides, dict):
        raise TypeError("SOD_SPARK_CONF_JSON must contain a JSON object")
    for key, value in overrides.items():
        builder = builder.config(str(key), str(value))
    return builder.getOrCreate()
