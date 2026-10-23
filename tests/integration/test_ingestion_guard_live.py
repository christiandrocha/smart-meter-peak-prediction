"""Reverse pre-check of the ingestion job on dev (AC-94 to AC-98; ADR 0013).

Run order (runbook "Evidence order", and the DESIGN): AC-94 first, right after
``databricks bundle deploy -t dev`` from a clean tree; then AC-97 (it needs no Kafka); then the
Kafka block ordered by the current Aiven state (AC-96, then the AC-28 and AC-30 tests of
``test_deployment.py``, then the PEAK_MODEL_CONCURRENCY suite and AC-98, then AC-95 in
``test_bronze_ingestion.py``). AC-96 starts one full ingestion run that the METER_INGESTION AC-30
test reuses. AC-97 starts one no-op pipeline update and two subset runs; the busy-case run uses
``require_idle=False`` because the busy state is what it tests.
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from smart_meter_peak_prediction import pipeline_guard

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
JOB_YAML = ROOT / "resources" / "smart_meter_ingestion.job.yml"
CHECK = "check_silver_gold_idle"
REFRESH = "refresh_silver_gold"
ENVIRONMENT_KEY = "ingestion_check_env"
CHECK_BUDGET_SECONDS = 120  # NFR-26, a measured target and not the 300 s task timeout
MAX_JOB_SECONDS = 3600  # AC-30
START_SLACK_SECONDS = 30  # an update is requested a moment before the pipeline task starts


def _yaml_tasks() -> dict[str, dict]:
    job = yaml.safe_load(JOB_YAML.read_text(encoding="utf-8"))["resources"]["jobs"]
    return {t["task_key"]: t for t in job["smart_meter_ingestion"]["tasks"]}


def _seconds(task: Any) -> float:
    return (task.end_time - task.start_time) / 1000


def _result(task: Any) -> str:
    state = task.state
    return state.result_state.value if state and state.result_state else ""


def _one(runner: Any, run: Any, key: str) -> Any:
    found = runner.task_runs_by_key(run).get(key, [])
    msg = f"expected exactly one task run of {key}, found {len(found)}: {run.run_page_url}"
    assert len(found) == 1, msg
    assert (found[0].attempt_number or 0) == 0, f"{key} was retried: {run.run_page_url}"
    return found[0]


def _ms(utc: str) -> float:
    return datetime.fromisoformat(utc.replace("Z", "+00:00")).timestamp() * 1000


def _updates_between(workspace: Any, pipeline_id: str, start_ms: int, end_ms: int) -> list[Any]:
    """Pipeline updates created in [start_ms, end_ms], newest first."""
    listed = workspace.pipelines.list_updates(pipeline_id, max_results=25).updates or []
    found = []
    for update in listed:
        created = pipeline_guard.utc_text(update.creation_time)
        if created is not None and start_ms // 1000 <= _ms(created) // 1000 <= end_ms // 1000:
            found.append(update)
    return found


def _assert_peak_job_idle(workspace: Any, peak_job: Any) -> None:
    active = list(workspace.jobs.list_runs(job_id=peak_job.job_id, active_only=True))
    assert not active, f"a smart_meter_peak_model run is active: {[r.run_id for r in active]}"


def _wait_pipeline_idle(workspace: Any, pipeline_id: str, minutes: int = 20) -> None:
    deadline = time.monotonic() + minutes * 60
    while True:
        state = workspace.pipelines.get(pipeline_id).state
        if state is not None and state.value == "IDLE":  # exactly IDLE, as assert_ingestion_idle
            return
        if time.monotonic() > deadline:
            raise AssertionError(f"the pipeline was still not IDLE after {minutes} min")
        time.sleep(10)


# ----------------------------------------------------------------------------- AC-94
def test_ac94_deployed_ingestion_job_equals_the_yaml(workspace, job, pipeline) -> None:
    """After validate and deploy (no cycle): the deployed job has the YAML's graph and settings."""
    deployed = workspace.jobs.get(job.job_id).settings
    expected = _yaml_tasks()
    actual = {t.task_key: t for t in deployed.tasks}
    assert set(actual) == set(expected)
    assert len(deployed.tasks) == 5
    for key, task in expected.items():
        got = actual[key]
        wanted_depends = sorted(d["task_key"] for d in task.get("depends_on", []))
        assert sorted(d.task_key for d in got.depends_on or []) == wanted_depends, key
        assert got.timeout_seconds == task["timeout_seconds"], key
        assert (got.max_retries or 0) == task["max_retries"], key
        wanted_optimization = bool(task.get("disable_auto_optimization"))
        assert bool(got.disable_auto_optimization) == wanted_optimization, key
    for key in ("ingest_kafka", CHECK):  # read back as 0 and true, not unset (A-27)
        assert actual[key].max_retries == 0, key
        assert actual[key].disable_auto_optimization is True, key
    parameters = actual[CHECK].notebook_task.base_parameters
    assert parameters["pipeline_id"] == pipeline.pipeline_id
    assert set(parameters) == {"src_path", "pipeline_id"}

    environments = deployed.environments or []
    assert [e.environment_key for e in environments] == [ENVIRONMENT_KEY]
    spec = environments[0].spec
    version = getattr(spec, "environment_version", None)
    if version is None:  # DA-32 fallback: the older field name
        raw = spec.as_dict()
        version = raw.get("environment_version") or raw.get("client")
    assert str(version) == "2"
    users = [t.task_key for t in deployed.tasks if t.environment_key]
    assert users == [CHECK]
    assert actual[CHECK].environment_key == ENVIRONMENT_KEY


# ----------------------------------------------------------------------------- AC-96
def test_ac96_full_run_passes_the_check_and_every_task_succeeds_once(
    workspace, job, peak_job, pipeline, peak_runner, evidence
) -> None:
    _assert_peak_job_idle(workspace, peak_job)
    run = peak_runner.run(job)  # asserts the pipeline and the ingestion job are idle first
    assert run.result_state == "SUCCESS", run.url
    tasks = {key: _one(peak_runner, run.run, key) for key in _yaml_tasks()}
    for key, task in tasks.items():
        assert _result(task) == "SUCCESS", key
    check = tasks[CHECK]
    assert _seconds(check) <= CHECK_BUDGET_SECONDS, f"the check needed {_seconds(check):.0f} s"
    value = run.outputs[CHECK]
    assert value["outcome"] == "idle"
    assert value["pipeline"]["pipeline_id"] == pipeline.pipeline_id
    assert value["checked_at"].endswith("Z")
    assert value["caller"] == {"job": "smart_meter_ingestion", "task": CHECK}

    refresh = tasks[REFRESH]
    updates = _updates_between(
        workspace,
        pipeline.pipeline_id,
        refresh.start_time - START_SLACK_SECONDS * 1000,
        refresh.end_time,
    )
    assert len(updates) == 1, f"updates created during refresh_silver_gold: {len(updates)}"
    assert updates[0].state.value == "COMPLETED"
    total = (run.run.end_time - run.run.start_time) / 1000
    assert total <= MAX_JOB_SECONDS, f"the run took {total:.0f} s"
    evidence.save(
        "ac96_ingestion_run",
        {
            "run_id": run.run.run_id,
            "run_seconds": total,
            "task_seconds": {key: _seconds(task) for key, task in tasks.items()},
            "check_exit_value": value,
        },
    )


# ----------------------------------------------------------------------------- AC-97
def test_ac97_check_refuses_while_an_update_is_active_and_the_rerun_succeeds(
    workspace, job, peak_job, pipeline, peak_runner
) -> None:
    peak_runner.assert_ingestion_idle()
    _assert_peak_job_idle(workspace, peak_job)
    subset = [CHECK, REFRESH]
    update_id = workspace.pipelines.start_update(
        pipeline_id=pipeline.pipeline_id, full_refresh=False
    ).update_id
    try:
        try:
            refused = peak_runner.run(job, only=subset, expect="FAILED", require_idle=False)
        except AssertionError as exc:
            msg = (
                f"{exc}. The update {update_id} may have ended before the check read it "
                "(DA-31); the no-op update lasted about 125 s on dev. Run the test again; then "
                "start the update with full_refresh=True; if it keeps passing vacuously record "
                "AC-97 as Partial with a direct pipeline_guard.check_pipeline read during the "
                "update."
            )
            raise AssertionError(msg) from exc
        check = _one(peak_runner, refused.run, CHECK)
        assert _result(check) == "FAILED"
        assert _seconds(check) <= CHECK_BUDGET_SECONDS
        error = refused.errors[CHECK]
        assert update_id in error
        assert "smart_meter_silver_gold" in error
        assert "rerun smart_meter_ingestion" in error
        assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", error)  # UTC with Z
        assert _result(_one(peak_runner, refused.run, REFRESH)) == "UPSTREAM_FAILED"
    finally:
        _wait_pipeline_idle(workspace, pipeline.pipeline_id)

    # the refused run requested no update of its own: none but U was created during its lifetime
    during = [
        u.update_id
        for u in _updates_between(
            workspace, pipeline.pipeline_id, refused.run.start_time, refused.run.end_time
        )
        if u.update_id != update_id
    ]
    assert during == [], f"updates created during the refused run: {during}"

    rerun = peak_runner.run(job, only=subset, require_idle=True)  # expect SUCCESS
    assert _result(_one(peak_runner, rerun.run, CHECK)) == "SUCCESS"
    assert _result(_one(peak_runner, rerun.run, REFRESH)) == "SUCCESS"
    assert rerun.outputs[CHECK]["outcome"] == "idle"


# ----------------------------------------------------------------------------- AC-98
def test_ac98_ac74_ingestion_run_passed_its_check_and_refresh(
    workspace, peak_runner, evidence
) -> None:
    """The ingestion side of the shipped AC-74 run: no mutual refusal (needs Aiven on)."""
    refused = evidence.load(
        "ac74_refused_run", "test_ac74_pre_check_refuses_a_run_while_ingestion_is_active"
    )
    run_id = refused["ingestion_run_id"]
    run = workspace.jobs.get_run(run_id)
    grouped = peak_runner.task_runs_by_key(run)
    stale = (
        f"ingestion run {run_id} has no {CHECK} task: stale evidence, rerun AC-74 after the deploy"
    )
    assert CHECK in grouped, stale
    upstream = [
        _result(t) for key in ("ingest_files", "ingest_kafka") for t in grouped.get(key, [])
    ]
    hint = (
        f"ingestion run {run_id}: ingest_files/ingest_kafka results {upstream}; the shipped AC-74 "
        "test needs the Aiven service on (and its Kafka reset after a power-off); run it again"
    )
    assert upstream
    assert all(r == "SUCCESS" for r in upstream), hint
    for key in (CHECK, REFRESH):
        entries = grouped.get(key, [])
        assert len(entries) == 1, f"{key}: expected one run in ingestion run {run_id}"
        assert _result(entries[0]) == "SUCCESS", f"{key} ended {_result(entries[0])!r}: {hint}"
