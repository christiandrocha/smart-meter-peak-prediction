"""Shared fixtures. The ``spark`` fixture is a local, UTC, small Spark session (no cluster)."""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

# Use the project's JDK when the shell has none (local development convenience).
_LOCAL_JDK = Path.home() / ".local" / "jdk17"
if "JAVA_HOME" not in os.environ and shutil.which("java") is None and _LOCAL_JDK.is_dir():
    os.environ["JAVA_HOME"] = str(_LOCAL_JDK)
    os.environ["PATH"] = f"{_LOCAL_JDK / 'bin'}{os.pathsep}{os.environ['PATH']}"


@pytest.fixture(scope="session")
def spark(tmp_path_factory: pytest.TempPathFactory) -> Iterator:
    from pyspark.sql import SparkSession

    warehouse = tmp_path_factory.mktemp("spark-warehouse")
    session = (
        SparkSession.builder.master("local[2]")
        .appName("smart-meter-unit-tests")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.default.parallelism", "2")
        .config("spark.sql.warehouse.dir", str(warehouse))
        .config("spark.ui.enabled", "false")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()
