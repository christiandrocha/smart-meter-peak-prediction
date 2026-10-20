# Databricks notebook source
# Idempotent setup of catalog, schemas, Volumes and Bronze tables (OD-05, ADR 0003, FR-17).
#
# Runs as the first task of the daily job and once by hand on a fresh workspace, between the two
# first-time deploys (DA-06): (1) `databricks bundle deploy -t dev` (files sync, pipeline creation
# fails because the catalog is absent), (2) run this notebook from the synced bundle files with its
# default widget values, (3) `databricks bundle deploy -t dev` again.
#
# Every statement is CREATE ... IF NOT EXISTS; a rerun changes nothing. The statements are built by
# `smart_meter_peak_prediction.catalog_setup` (tested). No secrets are used here.

# COMMAND ----------

import os
import sys

# `src_path` comes from the job (bundle files path). When run by hand it is empty and the package
# is found next to the notebooks folder of the synced bundle (the working directory of a workspace
# notebook is its folder).
dbutils.widgets.text("src_path", "")
_src = dbutils.widgets.get("src_path") or os.path.join(os.path.dirname(os.getcwd()), "src")
assert os.path.isdir(_src), "package folder not found; pass the src_path widget"
sys.path.insert(0, _src)

from smart_meter_peak_prediction.catalog_setup import setup_statements  # noqa: E402
from smart_meter_peak_prediction.config import Settings  # noqa: E402

# COMMAND ----------

_defaults = Settings()
_widget_names = (
    "catalog",
    "bronze_schema",
    "silver_schema",
    "gold_schema",
    "ml_schema",
)
for _name in _widget_names:
    dbutils.widgets.text(_name, getattr(_defaults, _name))
settings = Settings.from_mapping({name: dbutils.widgets.get(name) for name in _widget_names})

# Time is UTC end to end (golden rule 5).
spark.conf.set("spark.sql.session.timeZone", "UTC")
assert spark.conf.get("spark.sql.session.timeZone") == "UTC"

# COMMAND ----------

for statement in setup_statements(settings):
    spark.sql(statement)
print(f"setup complete for catalog {settings.catalog}")
