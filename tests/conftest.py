"""Shared local Spark session for the tests (skipped when no local JVM / real pyspark is available)."""
import shutil
import tempfile

import pytest


@pytest.fixture(scope="session")
def local_spark():
    try:
        from pyspark.sql import SparkSession
        wh = tempfile.mkdtemp(prefix="oi_sap_wh_")
        s = (SparkSession.builder.master("local[1]").appName("oi-tests")
             .config("spark.ui.enabled", "false").config("spark.sql.shuffle.partitions", "1").config("spark.driver.memory", "4g")
             .config("spark.sql.warehouse.dir", wh).getOrCreate())
    except Exception as e:  # noqa — e.g. databricks-connect's pyspark, no JVM
        pytest.skip(f"no local Spark: {e}")
    yield s
    s.stop()
    shutil.rmtree(wh, ignore_errors=True)
