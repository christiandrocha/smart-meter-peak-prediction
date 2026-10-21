# Databricks notebook source
# Weather file into the append-only Bronze table with Auto Loader `availableNow` (FR-18, AC-36).
#
# Precondition: the catalog and schemas exist (METER_INGESTION, ADR 0003) and the weather file was
# uploaded once to the `weather` folder of the landing Volume (runbook). The notebook creates the
# PEAK_MODEL plain Delta tables if missing (idempotent), then ingests. A rerun with no new file adds
# 0 rows (checkpoint). There is deliberately no try/except around the stream (I-14): a failure
# surfaces at notebook level and fails the task; the task timeout and retries are the policy.

# COMMAND ----------

import json
import os
import sys

dbutils.widgets.text("src_path", "")
_src = dbutils.widgets.get("src_path") or os.path.join(os.path.dirname(os.getcwd()), "src")
assert os.path.isdir(_src), "package folder not found; pass the src_path widget"
sys.path.insert(0, _src)

from smart_meter_peak_prediction import bronze, peak_config, peak_setup, weather  # noqa: E402
from smart_meter_peak_prediction.config import Settings  # noqa: E402

# COMMAND ----------

_defaults = Settings()
_widget_names = ("catalog", "bronze_schema", "silver_schema", "gold_schema", "ml_schema")
for _name in _widget_names:
    dbutils.widgets.text(_name, getattr(_defaults, _name))
settings = Settings.from_mapping({name: dbutils.widgets.get(name) for name in _widget_names})

# Time is UTC end to end (golden rule 5).
spark.conf.set("spark.sql.session.timeZone", "UTC")
assert spark.conf.get("spark.sql.session.timeZone") == "UTC"

# COMMAND ----------

# Precondition (schemas exist) and CREATE TABLE IF NOT EXISTS for the four plain Delta tables.
peak_setup.ensure_tables(spark, settings)

# COMMAND ----------

bronze_table = peak_config.bronze_weather_table(settings)
stream = weather.project_weather(
    bronze.auto_loader_reader(
        spark, weather.WEATHER_SOURCE_SCHEMA, peak_config.weather_landing_path(settings)
    )
)
bronze.run_available_now(stream, bronze_table, peak_config.weather_checkpoint(settings))

# COMMAND ----------

result = {"table": bronze_table, "row_count": spark.table(bronze_table).count()}
print(result)
dbutils.notebook.exit(json.dumps(result))  # prints are not returned by the Jobs API
