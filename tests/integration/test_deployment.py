"""Deployed job, pipeline and catalog layout, and the daily run duration (AC-28, AC-30).

The first-deploy sequence of DA-06 (deploy, run ``notebooks/setup_catalog.py``, deploy again) is a
manual step; its exit codes go into the build report. These tests check the result.
"""

from __future__ import annotations

import pytest

from smart_meter_peak_prediction.bronze import BRONZE_TABLES
from smart_meter_peak_prediction.config import LAYERS

pytestmark = pytest.mark.integration

JOB_NAME = "smart_meter_ingestion"
PIPELINE_NAME = "smart_meter_silver_gold"
JOB_TASKS = ("setup_catalog", "ingest_files", "ingest_kafka", "refresh_silver_gold")
MAX_JOB_SECONDS = 3600  # AC-30
PIPELINE_REVISIT_SECONDS = 900  # ADR 0005 revisit trigger: refresh longer than 15 minutes
QUARTZ_DAILY_0600 = "0 0 6 * * ?"


def test_ac28_deployed_job_pipeline_and_catalog_layout(
    workspace, settings, job, pipeline, strip_dev_prefix
) -> None:
    assert strip_dev_prefix(job.settings.name) == JOB_NAME
    assert strip_dev_prefix(pipeline.name) == PIPELINE_NAME
    schedule = job.settings.schedule
    assert schedule is not None
    assert schedule.quartz_cron_expression == QUARTZ_DAILY_0600
    assert schedule.timezone_id == "UTC"
    assert schedule.pause_status.value == "PAUSED"  # development mode
    assert {task.task_key for task in job.settings.tasks} == set(JOB_TASKS)

    schemas = {s.name for s in workspace.schemas.list(catalog_name=settings.catalog)}
    expected = {settings.schema(layer) for layer in LAYERS}
    assert expected <= schemas, f"missing schemas: {sorted(expected - schemas)}"
    bronze = settings.schema("bronze")
    volumes = {v.name for v in workspace.volumes.list(settings.catalog, bronze)}
    assert {"landing", "checkpoints"} <= volumes
    tables = {t.name for t in workspace.tables.list(settings.catalog, bronze)}
    assert set(BRONZE_TABLES) <= tables
    assert job.settings.name.endswith(JOB_NAME)  # raw name: optional prefix plus the base name


def test_ac30_daily_job_run_within_60_minutes(workspace, job, full_runs, evidence) -> None:
    """The latest successful run of all four tasks finished within the budget."""
    successful = full_runs()
    hint = "no successful full job run: run `databricks bundle run smart_meter_ingestion`"
    assert successful, hint
    run = workspace.jobs.get_run(successful[0].run_id)
    for task in run.tasks:
        assert task.state.result_state.value == "SUCCESS", task.task_key
    assert run.status.termination_details.code.value == "SUCCESS"  # no quota termination
    seconds = (run.end_time - run.start_time) / 1000
    assert seconds <= MAX_JOB_SECONDS, f"the run took {seconds:.0f} s"

    by_task = {t.task_key: (t.end_time - t.start_time) / 1000 for t in run.tasks}
    evidence.save(
        "ac30_latest_run",
        {
            "run_id": run.run_id,
            "run_seconds": seconds,
            "task_seconds": by_task,
            "pipeline_over_revisit_trigger": by_task["refresh_silver_gold"]
            > PIPELINE_REVISIT_SECONDS,
        },
    )
