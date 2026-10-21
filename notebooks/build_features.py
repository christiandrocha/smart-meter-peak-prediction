# Databricks notebook source
# Dense daily feature table `ml.household_features_daily` (FR-20, AC-39 to AC-41, AC-66; ADR 0011).
#
# Recomputed in full from Gold, `silver.households` and `silver.weather_hourly`, checked (G-10),
# then written with one change-only MERGE into the Unity Catalog feature table (time-series column
# `feature_date`). A rerun with no new input reports 0 inserted, 0 updated, 0 deleted.
# No try/except (I-14).

# COMMAND ----------

# MAGIC %pip install --quiet databricks-feature-engineering==0.18.2 scikit-learn==1.3.0

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import json  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402
from datetime import date  # noqa: E402

dbutils.widgets.text("src_path", "")
_src = dbutils.widgets.get("src_path") or os.path.join(os.path.dirname(os.getcwd()), "src")
assert os.path.isdir(_src), "package folder not found; pass the src_path widget"
sys.path.insert(0, _src)

from databricks.feature_engineering import FeatureEngineeringClient  # noqa: E402

from smart_meter_peak_prediction import (  # noqa: E402
    delta_sync,
    features,
    peak_config,
    peak_setup,
    registry,
)
from smart_meter_peak_prediction.config import Settings  # noqa: E402
from smart_meter_peak_prediction.peak_config import PeakParameters  # noqa: E402

# G-01: the pinned library versions are the ones installed.
library_versions = peak_config.check_versions()

# COMMAND ----------

_defaults = Settings()
_settings_names = ("catalog", "bronze_schema", "silver_schema", "gold_schema", "ml_schema")
_parameter_names = ("baseline_day_count", "label_lookback_weeks")
_widget_names = (
    "catalog",
    "bronze_schema",
    "silver_schema",
    "gold_schema",
    "ml_schema",
    "baseline_day_count",
    "label_lookback_weeks",
)
_parameter_defaults = PeakParameters()
for _name in _settings_names:
    dbutils.widgets.text(_name, getattr(_defaults, _name))
for _name in _parameter_names:
    dbutils.widgets.text(_name, str(getattr(_parameter_defaults, _name)))
settings = Settings.from_mapping({name: dbutils.widgets.get(name) for name in _settings_names})
params = PeakParameters.from_mapping({name: dbutils.widgets.get(name) for name in _parameter_names})

spark.conf.set("spark.sql.session.timeZone", "UTC")
assert spark.conf.get("spark.sql.session.timeZone") == "UTC"

# COMMAND ----------

fe = FeatureEngineeringClient()
features_table = peak_config.features_table(settings)

peak_setup.ensure_tables(spark, settings)
created = registry.ensure_feature_table(
    fe, spark, features_table, peak_setup.feature_table_schema()
)
spark.sql(peak_setup.feature_retention_sql(settings))  # 90-day history retention (ADR 0011)

# COMMAND ----------

households = spark.table(peak_config.silver_households_table(settings))
daily = spark.table(peak_config.gold_daily_table(settings))
silver_weather = spark.table(peak_config.silver_weather_table(settings))
study_start = date.fromisoformat(settings.study_start)

computed = features.build_features(households, daily, silver_weather, params, study_start)
row_count = features.check_features(  # G-10 and the not-null columns
    computed, households, study_start, features.latest_reading_date(daily)
)
metrics = delta_sync.merge_changes(
    spark, computed, features_table, ["household_id", "feature_date"], "features_recomputed"
)
spark.sql(delta_sync.set_properties_sql(features_table, features.feature_table_properties(params)))

# COMMAND ----------

result = {
    "table": features_table,
    "created": created,
    "row_count": row_count,
    "table_version": registry.table_version(spark, features_table),
    "parameters": params.feature_properties(),
    "libraries": library_versions,
    "merge": metrics,
}
print(result)
dbutils.notebook.exit(json.dumps(result))
