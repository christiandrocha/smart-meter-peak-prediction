# Databricks notebook source
# Label and eligibility table `ml.household_labels_daily` (FR-21, FR-22, AC-44 to AC-47, AC-63,
# AC-66; ADR 0010, ADR 0011).
#
# The label and eligibility parameters are job parameters (widgets, FR-31). They are printed,
# returned in the exit value and stored as table properties, so a training run can read the
# parameters of the labels it uses. QR-19 and G-10 run inside `labels.build_labels` before the
# MERGE. A rerun with no new input reports 0 inserted, 0 updated, 0 deleted. No try/except (I-14).

# COMMAND ----------

import json
import os
import sys
from datetime import date

dbutils.widgets.text("src_path", "")
_src = dbutils.widgets.get("src_path") or os.path.join(os.path.dirname(os.getcwd()), "src")
assert os.path.isdir(_src), "package folder not found; pass the src_path widget"
sys.path.insert(0, _src)

from smart_meter_peak_prediction import delta_sync, labels, peak_config, peak_setup  # noqa: E402
from smart_meter_peak_prediction.config import Settings  # noqa: E402
from smart_meter_peak_prediction.peak_config import PeakParameters  # noqa: E402

# COMMAND ----------

_defaults = Settings()
_settings_names = ("catalog", "bronze_schema", "silver_schema", "gold_schema", "ml_schema")
_parameter_names = (
    "label_threshold",
    "baseline_day_count",
    "label_lookback_weeks",
    "coverage_min",
    "zero_share_max",
    "eligibility_months",
)
_widget_names = (
    "catalog",
    "bronze_schema",
    "silver_schema",
    "gold_schema",
    "ml_schema",
    "label_threshold",
    "baseline_day_count",
    "label_lookback_weeks",
    "coverage_min",
    "zero_share_max",
    "eligibility_months",
)
_parameter_defaults = PeakParameters()
for _name in _settings_names:
    dbutils.widgets.text(_name, getattr(_defaults, _name))
for _name in _parameter_names:
    dbutils.widgets.text(_name, str(getattr(_parameter_defaults, _name)))
settings = Settings.from_mapping({name: dbutils.widgets.get(name) for name in _settings_names})
# Only declared widget names are read; an invalid value stops the task here (G-09).
params = PeakParameters.from_mapping({name: dbutils.widgets.get(name) for name in _parameter_names})
print("label and eligibility parameters:", params.label_properties())

spark.conf.set("spark.sql.session.timeZone", "UTC")
assert spark.conf.get("spark.sql.session.timeZone") == "UTC"

# COMMAND ----------

labels_table = peak_config.labels_table(settings)
peak_setup.ensure_tables(spark, settings)

households = spark.table(peak_config.silver_households_table(settings))
daily = spark.table(peak_config.gold_daily_table(settings))
monthly = spark.table(peak_config.gold_monthly_table(settings))

computed = labels.build_labels(  # QR-19 and G-10 raise before any write
    households, daily, monthly, params, date.fromisoformat(settings.study_start)
)
metrics = delta_sync.merge_changes(
    spark, computed, labels_table, ["household_id", "target_date"], "labels_recomputed"
)
spark.sql(delta_sync.set_properties_sql(labels_table, labels.label_table_properties(params)))

# COMMAND ----------

labelled = spark.table(labels_table).where("label_consumption_spike IS NOT NULL")
result = {
    "table": labels_table,
    "row_count": spark.table(labels_table).count(),
    "labelled_count": labelled.count(),
    "positive_count": labelled.where("label_consumption_spike = 1").count(),
    "eligible_labelled_count": labelled.where("is_eligible").count(),
    "parameters": params.label_properties(),
    "merge": metrics,
}
print(result)
dbutils.notebook.exit(json.dumps(result))
