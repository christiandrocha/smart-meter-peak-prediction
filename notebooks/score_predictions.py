# Databricks notebook source
# Daily scoring (FR-28, FR-29, AC-56 to AC-61; ADR 0009).
#
# Scores the households eligible on each target date T with the version that alias `champion`
# resolves to at the start of the run (pinned for the whole run), through `fe.score_batch`, and
# replaces only the prediction rows of the scored dates. `target_date` empty means the latest
# complete Gold day + 1; `target_date_end` makes a backfill range. G-06, G-07 and QR-20 raise before
# the write, so a failed run changes 0 rows. No try/except (I-14).

# COMMAND ----------

# MAGIC %pip install --quiet databricks-feature-engineering==0.18.2 scikit-learn==1.3.0

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import json  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402

dbutils.widgets.text("src_path", "")
_src = dbutils.widgets.get("src_path") or os.path.join(os.path.dirname(os.getcwd()), "src")
assert os.path.isdir(_src), "package folder not found; pass the src_path widget"
sys.path.insert(0, _src)

import mlflow  # noqa: E402
from databricks.feature_engineering import FeatureEngineeringClient  # noqa: E402
from mlflow import MlflowClient  # noqa: E402

from smart_meter_peak_prediction import peak_config, peak_setup, registry, scoring  # noqa: E402
from smart_meter_peak_prediction.config import Settings  # noqa: E402
from smart_meter_peak_prediction.peak_config import PeakParameters  # noqa: E402

# G-01: the pinned library versions are the ones installed.
library_versions = peak_config.check_versions()

# COMMAND ----------

_defaults = Settings()
_settings_names = ("catalog", "bronze_schema", "silver_schema", "gold_schema", "ml_schema")
_parameter_names = ("target_date", "target_date_end")
_widget_names = (
    "catalog",
    "bronze_schema",
    "silver_schema",
    "gold_schema",
    "ml_schema",
    "target_date",
    "target_date_end",
)
for _name in _settings_names:
    dbutils.widgets.text(_name, getattr(_defaults, _name))
for _name in _parameter_names:
    dbutils.widgets.text(_name, "")  # empty: latest complete Gold day + 1
settings = Settings.from_mapping({name: dbutils.widgets.get(name) for name in _settings_names})
params = PeakParameters.from_mapping({name: dbutils.widgets.get(name) for name in _parameter_names})

spark.conf.set("spark.sql.session.timeZone", "UTC")
assert spark.conf.get("spark.sql.session.timeZone") == "UTC"

# COMMAND ----------

mlflow.set_registry_uri("databricks-uc")
fe = FeatureEngineeringClient()
client = MlflowClient()
model_name = peak_config.model_name(settings)
predictions_table = peak_config.predictions_table(settings)

peak_setup.ensure_tables(spark, settings)

result = scoring.run(
    daily=spark.table(peak_config.gold_daily_table(settings)),
    labels=spark.table(peak_config.labels_table(settings)),
    features=spark.table(peak_config.features_table(settings)),
    households=spark.table(peak_config.silver_households_table(settings)),
    params=params,
    champion=lambda: registry.resolve_champion(client, model_name),
    model_name=model_name,
    scorer=registry.fe_scorer(fe),
    writer=scoring.table_writer(predictions_table),
)

# COMMAND ----------

summary = {
    **result.summary(),
    "model": model_name,
    "table": predictions_table,
    "libraries": library_versions,
}
print(summary)
dbutils.notebook.exit(json.dumps(summary))
