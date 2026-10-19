"""Deployed job, pipeline and catalog layout, and the daily run duration (AC-28, AC-30).

The first-deploy sequence of DA-06 (deploy, run ``notebooks/setup_catalog.py``, deploy again) is a
manual step; its exit codes go into the build report. These tests check the result.
"""

from __future__ import annotations

import pytest

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


def test_ac30_daily_job_run_within_60_minutes(workspace, job, evidence) -> None:
    """The latest successful run finished all four tasks within the budget."""
    runs = list(workspace.jobs.list_runs(job_id=job.job_id, completed_only=True, limit=25))
    successful = [
        r
        for r in runs
        if r.state and r.state.result_state and r.state.result_state.value == "SUCCESS"
    ]
    assert successful, "no successful job run: run `databricks bundle run smart_meter_ingestion`"
    latest = max(successful, key=lambda r: r.start_time)
    run = workspace.jobs.get_run(latest.run_id)
    assert {t.task_key for t in run.tasks} == set(JOB_TASKS)
    for task in run.tasks:
        assert task.state.result_state.value == "SUCCESS", task.task_key
    assert run.status.termination_details.code.value == "SUCCESS"  # no quota termination
    seconds = (run.end_time - run.start_time) / 1000
    assert seconds <= MAX_JOB_SECONDS, f"the run took {seconds:.0f} s"

    by_task = {t.task_key: (t.end_time - t.start_time) / 1000 for t in run.tasks}
    pipeline_seconds = by_task["refresh_silver_gold"]
    newer_failures = [r.run_id for r in runs if r.start_time > latest.start_time]
    evidence.save(
        "ac30_latest_run",
        {
            "run_id": run.run_id,
            "run_seconds": seconds,
            "task_seconds": by_task,
            "pipeline_over_revisit_trigger": pipeline_seconds > PIPELINE_REVISIT_SECONDS,
            "newer_unsuccessful_runs": newer_failures,
        },
    )
