# Databricks notebook source
# Read-only pre-check before refresh_silver_gold (FR-33 to FR-38, AC-68 to AC-73; ADR 0012).
#
# The ingestion job and this job start updates of one pipeline, which accepts one update at a time.
# This task reads the active runs of the ingestion job and the latest updates of the pipeline with
# the job's own identity (default notebook authentication, no secret) and fails at once, naming the
# blocking run or update, when either is active. When it cannot read the state it fails closed. The
# decision logic is `pipeline_guard`. No try/except (I-14): a failure ends the task FAILED and the
# error text is the operator message. The ids are bundle references passed as task parameters.

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

_widget_names = ("ingestion_job_id", "pipeline_id")
for _name in _widget_names:
    dbutils.widgets.text(_name, "")  # empty fails closed (G-13)

# Time is UTC end to end (golden rule 5).
spark.conf.set("spark.sql.session.timeZone", "UTC")
assert spark.conf.get("spark.sql.session.timeZone") == "UTC"

# COMMAND ----------

from databricks.sdk import WorkspaceClient  # noqa: E402
from databricks.sdk.config import Config  # noqa: E402

# The timeouts are Config fields; WorkspaceClient(retry_timeout_seconds=...) is a TypeError in
# databricks-sdk 0.40.0, the version of serverless environment version 2 (DA-20).
report = pipeline_guard.run(
    lambda: WorkspaceClient(config=Config(**pipeline_guard.CLIENT_LIMITS)),
    dbutils.widgets.get("ingestion_job_id"),
    dbutils.widgets.get("pipeline_id"),
)
print(report.message())
result = pipeline_guard.enforce(report)  # raises PipelineGuardError on busy or unknown

# COMMAND ----------

dbutils.notebook.exit(json.dumps(result))
