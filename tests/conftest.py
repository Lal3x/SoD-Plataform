import os
import shutil
from pathlib import Path

import pytest

from sod_platform.bronze.ingestion.spark import create_spark_session


@pytest.fixture(scope="module")
def spark(tmp_path_factory: pytest.TempPathFactory):
    """A small, isolated Spark runtime for tests that need Iceberg."""
    if shutil.which("java") is None:
        pytest.skip("Spark integration tests require a Java runtime")
    warehouse = tmp_path_factory.mktemp("iceberg-warehouse")
    previous = {
        key: os.environ.get(key)
        for key in (
            "SOD_WAREHOUSE",
            "SPARK_MASTER",
            "SPARK_SHUFFLE_PARTITIONS",
            "SOD_SPARK_CONF_JSON",
        )
    }
    os.environ.update(
        {
            "SOD_WAREHOUSE": str(warehouse),
            "SPARK_MASTER": "local[2]",
            "SPARK_SHUFFLE_PARTITIONS": "2",
            "SOD_SPARK_CONF_JSON": '{"spark.sql.autoBroadcastJoinThreshold":"-1","spark.sql.adaptive.enabled":"false"}',
        }
    )
    session = create_spark_session(Path.cwd(), "sod-platform-integration-tests")
    try:
        yield session
    finally:
        session.catalog.clearCache()
        session.stop()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(autouse=True)
def clear_spark_cache(request: pytest.FixtureRequest):
    """Keep cached plans/data from affecting the next test in the session."""
    yield
    if "spark" in request.fixturenames:
        request.getfixturevalue("spark").catalog.clearCache()
