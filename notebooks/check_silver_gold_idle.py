# Databricks notebook source
# Read-only reverse pre-check before refresh_silver_gold of smart_meter_ingestion (FR-44 to FR-49,
# AC-86 to AC-91; ADR 0013). Reads only the shared pipeline with the job's own identity (default
# notebook authentication, no secret) and fails at once, naming the active update, when it is busy;
# fails closed when it cannot read the state. No try/except (I-14). The pipeline id is a bundle
# reference passed as a task parameter; no job id (A-30).

# COMMAND ----------

import json
import os
import sys

dbutils.widgets.text("src_path", "")
_src = dbutils.widgets.get("src_path") or os.path.join(os.path.dirname(os.getcwd()), "src")
assert os.path.isdir(_src), "package folder not found; pass the src_path widget"
sys.path.insert(0, _src)

from smart_meter_peak_prediction import pipeline_guard  # noqa: E402

# COMMAND ----------

_widget_names = ("pipeline_id",)
for _name in _widget_names:
    dbutils.widgets.text(_name, "")  # empty fails closed (G-22)

spark.conf.set("spark.sql.session.timeZone", "UTC")  # golden rule 5
assert spark.conf.get("spark.sql.session.timeZone") == "UTC"

# COMMAND ----------

from databricks.sdk import WorkspaceClient  # noqa: E402
from databricks.sdk.config import Config  # noqa: E402
from databricks.sdk.version import __version__ as sdk_version  # noqa: E402

print(f"databricks-sdk {sdk_version}")  # SDK drift shows in the task output (F-04)
report = pipeline_guard.run_pipeline_check(
    lambda: WorkspaceClient(config=Config(**pipeline_guard.CLIENT_LIMITS)),
    dbutils.widgets.get("pipeline_id"),
    caller=pipeline_guard.INGESTION_CALLER,
)
print(report.message())
result = pipeline_guard.enforce_pipeline(report)  # raises PipelineGuardError on busy or unknown

# COMMAND ----------

dbutils.notebook.exit(json.dumps(result))
