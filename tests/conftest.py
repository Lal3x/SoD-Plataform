import shutil
from pathlib import Path

import pytest

from sod_platform.bronze.ingestion.spark import create_spark_session


@pytest.fixture(scope="module")
def spark(tmp_path_factory: pytest.TempPathFactory):
    if shutil.which("java") is None:
        pytest.skip("Spark integration tests require a Java runtime")
    warehouse = tmp_path_factory.mktemp("iceberg-warehouse")
    import os

    os.environ["SOD_WAREHOUSE"] = str(warehouse)
    session = create_spark_session(Path.cwd(), "sod-platform-integration-tests")
    yield session
    session.stop()
