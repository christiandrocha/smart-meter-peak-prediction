# Databricks notebook source
# Spike 06 (DA-20, DA-22, DA-23; informs DA-26). Throwaway code, never imported by src/.
# Run it through 06_spike_pipeline_guard_probe_submit.py, which submits it as a one-time
# serverless notebook task on environment version 2, the environment of the PEAK_MODEL job.
#
# Questions (DESIGN_PEAK_MODEL_CONCURRENCY, ADR 0012)
#   DA-20  Environment version 2 ships databricks-sdk with jobs.list_runs(active_only),
#          jobs.list(name) and pipelines.get(...).latest_updates; WorkspaceClient() authenticates
#          in a notebook task with no configuration; the client takes retry_timeout_seconds and
#          http_timeout_seconds (through Config in 0.40.0).
#   DA-22  pipelines.get(id).latest_updates[0] shows an update with its update_id, state and
#          creation_time (the submit script reads it every 2 s during an update; this notebook
#          records what it sees at its own read time).
#   DA-23  jobs.list(name=<deployed name>) returns exactly the ingestion job.
#
# Pass criteria
#   DA-20: the imports, the client with both timeout keywords and every read below succeed with
#          no %pip install.
#   DA-23: jobs.list(name=deployed name) returns exactly one job, the ingestion job id.
#
# Read-only: no call starts, stops or changes any object. The result is the notebook exit value.

# COMMAND ----------

import json
import time

import databricks.sdk
from databricks.sdk import WorkspaceClient
from databricks.sdk.config import Config

dbutils.widgets.text("ingestion_job_id", "")  # noqa: F821
dbutils.widgets.text("pipeline_id", "")  # noqa: F821
ingestion_job_id = int(dbutils.widgets.get("ingestion_job_id"))  # noqa: F821
pipeline_id = dbutils.widgets.get("pipeline_id")  # noqa: F821

out: dict = {
    "sdk_version": databricks.sdk.version.__version__,
    "read_at_ms": int(time.time() * 1000),
}

# databricks-sdk 0.40.0 (environment 2) has no timeout keywords on WorkspaceClient; the timeouts
# are Config fields, passed with config= (first run of this spike, 2026-10-22).
try:
    cfg = Config(retry_timeout_seconds=60, http_timeout_seconds=30)
    w = WorkspaceClient(config=cfg)
    out["client_with_timeouts"] = "ok"
    out["client_timeouts"] = [cfg.retry_timeout_seconds, cfg.http_timeout_seconds]
except Exception as exc:  # noqa: BLE001
    out["client_with_timeouts"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    w = WorkspaceClient()

out["run_as"] = w.current_user.me().user_name

job = w.jobs.get(ingestion_job_id)
out["ingestion_job_name"] = job.settings.name
same_name = list(w.jobs.list(name=job.settings.name))
out["jobs_list_by_name_ids"] = [j.job_id for j in same_name]
active = list(w.jobs.list_runs(job_id=ingestion_job_id, active_only=True))
out["ingestion_active_runs"] = [
    {"run_id": r.run_id, "life_cycle_state": str(r.state.life_cycle_state)} for r in active
]

pipeline = w.pipelines.get(pipeline_id)
out["pipeline_name"] = pipeline.name
out["pipeline_state"] = str(pipeline.state)
out["latest_updates"] = [
    {
        "update_id": u.update_id,
        "state": str(u.state),
        "creation_time": u.creation_time,
        "creation_time_type": type(u.creation_time).__name__,
    }
    for u in (pipeline.latest_updates or [])[:3]
]

dbutils.notebook.exit(json.dumps(out))  # noqa: F821
