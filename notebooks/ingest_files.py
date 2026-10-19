# Databricks notebook source
# Auto Loader `availableNow` into the append-only Bronze file tables (FR-04, AC-05, AC-06).
#
# Readings first, then households, each with its own checkpoint in the `checkpoints` Volume. A rerun
# with no new file adds 0 rows (checkpoint). There is deliberately no try/except around the streams
# (I-14): a failure surfaces at notebook level and fails the task; the task timeout and retries
# of the job are the failure policy.

# COMMAND ----------

import os
import sys

dbutils.widgets.text("src_path", "")
_src = dbutils.widgets.get("src_path") or os.path.join(os.path.dirname(os.getcwd()), "src")
assert os.path.isdir(_src), "package folder not found; pass the src_path widget"
sys.path.insert(0, _src)

from smart_meter_peak_prediction import bronze  # noqa: E402
from smart_meter_peak_prediction.config import (  # noqa: E402
    BRONZE_FILES_HOUSEHOLDS,
    BRONZE_FILES_READINGS,
    Settings,
)

# COMMAND ----------

_defaults = Settings()
_widget_names = ("catalog", "bronze_schema")
for _name in _widget_names:
    dbutils.widgets.text(_name, getattr(_defaults, _name))
settings = Settings.from_mapping({name: dbutils.widgets.get(name) for name in _widget_names})

spark.conf.set("spark.sql.session.timeZone", "UTC")
assert spark.conf.get("spark.sql.session.timeZone") == "UTC"

# COMMAND ----------

readings = bronze.project_files_readings(
    bronze.auto_loader_reader(
        spark, bronze.FILES_READINGS_SOURCE_SCHEMA, settings.landing_readings_path
    )
)
bronze.run_available_now(
    readings, settings.bronze_files_readings, settings.checkpoint(BRONZE_FILES_READINGS)
)

# COMMAND ----------

households = bronze.project_files_households(
    bronze.auto_loader_reader(
        spark, bronze.FILES_HOUSEHOLDS_SOURCE_SCHEMA, settings.landing_households_path
    )
)
bronze.run_available_now(
    households, settings.bronze_files_households, settings.checkpoint(BRONZE_FILES_HOUSEHOLDS)
)

# COMMAND ----------

for _table in (settings.bronze_files_readings, settings.bronze_files_households):
    print(f"{_table}: {spark.table(_table).count()} rows")
