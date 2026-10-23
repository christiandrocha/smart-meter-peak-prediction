# Databricks notebook source
# Spike 07 (A-26, A-29, A-30). Throwaway code, never imported by src/.
# Runs as the probe task of spike_07_guarded, on environment version 2 inside a job whose other
# tasks use the default environment.
#
# Pass criteria
#   A-26: this task runs on environment version 2 (databricks-sdk 0.40.0, as in spike 06) while
#         the other tasks of the same run use the default environment.
#   A-29: the job's run-as identity reads pipelines.get(id) with its state and latest_updates,
#         with no extra grant.
#   A-30: other_job_id arrives as a resolved numeric job id (the one-way reference works).
#
# Read-only: no call starts, stops or changes any object. The result is the notebook exit value.

# COMMAND ----------

import json
import sys

import databricks.sdk
from databricks.sdk import WorkspaceClient
from databricks.sdk.config import Config

dbutils.widgets.text("pipeline_id", "")  # noqa: F821
dbutils.widgets.text("other_job_id", "")  # noqa: F821
pipeline_id = dbutils.widgets.get("pipeline_id")  # noqa: F821
other_job_id = dbutils.widgets.get("other_job_id")  # noqa: F821

out: dict = {
    "sdk_version": databricks.sdk.version.__version__,
    "python": sys.version.split()[0],
    "other_job_id": other_job_id,
    "other_job_id_numeric": other_job_id.isdigit(),
}

try:
    w = WorkspaceClient(config=Config(retry_timeout_seconds=60, http_timeout_seconds=30))
    pipeline = w.pipelines.get(pipeline_id)
    out["pipeline_read"] = "ok"
    out["pipeline_state"] = str(pipeline.state)
    out["latest_updates"] = [
        {"update_id": u.update_id, "state": str(u.state), "creation_time": u.creation_time}
        for u in (pipeline.latest_updates or [])[:3]
    ]
except Exception as exc:  # noqa: BLE001
    out["pipeline_read"] = f"{type(exc).__name__}: {str(exc)[:300]}"

dbutils.notebook.exit(json.dumps(out))  # noqa: F821
