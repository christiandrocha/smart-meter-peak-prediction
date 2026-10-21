# Databricks notebook source
# Silver hourly weather: recompute from all of Bronze, check, change-only MERGE (FR-19, AC-37,
# AC-38, AC-66; ADR 0011).
#
# QR-16 (time parses) and QR-18 parse (temperature is a number) raise before any write, so a failed
# run commits 0 rows. QR-17 losers and QR-18 range warnings are counted in the exit value. A rerun
# with no new input reports 0 inserted, 0 updated, 0 deleted. No try/except (I-14).

# COMMAND ----------

import json
import os
import sys

dbutils.widgets.text("src_path", "")
_src = dbutils.widgets.get("src_path") or os.path.join(os.path.dirname(os.getcwd()), "src")
assert os.path.isdir(_src), "package folder not found; pass the src_path widget"
sys.path.insert(0, _src)

from smart_meter_peak_prediction import delta_sync, peak_config, weather  # noqa: E402
from smart_meter_peak_prediction.config import Settings  # noqa: E402

# COMMAND ----------

_defaults = Settings()
_widget_names = ("catalog", "bronze_schema", "silver_schema", "gold_schema", "ml_schema")
for _name in _widget_names:
    dbutils.widgets.text(_name, getattr(_defaults, _name))
settings = Settings.from_mapping({name: dbutils.widgets.get(name) for name in _widget_names})

spark.conf.set("spark.sql.session.timeZone", "UTC")
assert spark.conf.get("spark.sql.session.timeZone") == "UTC"

# COMMAND ----------

bronze_table = peak_config.bronze_weather_table(settings)
silver_table = peak_config.silver_weather_table(settings)

# QR-16 and QR-18 parse raise inside `silver_weather`, before anything is written.
silver = weather.silver_weather(spark.table(bronze_table))
if silver.row_count == 0:  # an empty Bronze would delete every Silver row via the MERGE
    raise RuntimeError(f"{bronze_table} is empty: upload the weather file and run ingest_weather")
metrics = delta_sync.merge_changes(
    spark, silver.frame, silver_table, ["weather_ts"], "silver_weather_recomputed"
)

# COMMAND ----------

result = {
    "table": silver_table,
    "row_count": silver.row_count,
    "duplicate_count": silver.duplicate_count,  # QR-17 losers
    "out_of_range_count": silver.out_of_range_count,  # QR-18 warn
    "merge": metrics,
}
print(result)
dbutils.notebook.exit(json.dumps(result))
