"""Pre-check before the shared pipeline task on dev (AC-74 to AC-77; ADR 0012).

Run order (runbook "Evidence order", and the DESIGN): AC-76, then AC-74, then AC-77 (it needs the
snapshots of both), then AC-75. Prerequisites: ``databricks bundle deploy -t dev`` from a clean
tree, a trained ``champion``, and idle ingestion job and pipeline.

AC-74 starts ``smart_meter_ingestion`` (user decision U-02: the Aiven Kafka service is on, so the
ingestion run reaches its own ``refresh_silver_gold``). AC-75 starts one no-op pipeline update. The
busy-case runs use ``require_idle=False`` because the busy state is what they test.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import pytest

from smart_meter_peak_prediction import pipeline_guard

pytestmark = pytest.mark.integration

DAILY_TASKS = (
    "check_pipeline_idle",
    "refresh_silver_gold",
    "ingest_weather",
    "build_weather_silver",
    "build_features",
    "build_labels",
    "score_predictions",
)
BLOCKED_TASKS = ("refresh_silver_gold", "build_features", "build_labels", "score_predictions")
PRE_CHECK_BUDGET_SECONDS = 120  # NFR-19, a measured target and not the 300 s task timeout
REFUSAL_TEXT = "Pipeline update already in progress."
PREDICTION_COLUMNS = ["household_id", "target_date", "score", "label", "model_version"]


def _seconds(task: Any) -> float:
    return (task.end_time - task.start_time) / 1000


def _result(task: Any) -> str:
    state = task.state
    return state.result_state.value if state and state.result_state else ""


def _only_task(runner: Any, run: Any, key: str) -> Any:
    found = runner.task_runs_by_key(run).get(key, [])
    count = len(found)
    msg = f"expected exactly one task run of {key}, found {count}: {run.run_page_url}"
    assert count == 1, msg
    return found[0]


def _prediction_snapshot(sql: Any, table: str, day: str) -> dict[str, Any]:
    """Row count, checksum without ``_scored_at`` and the newest ``_scored_at`` of one date."""
    columns = ", ".join(f"`{c}`" for c in PREDICTION_COLUMNS)
    row = sql.one(
        f"SELECT count(*) AS n, "
        f"CAST(sum(CAST(xxhash64({columns}) AS DECIMAL(38,0))) AS STRING) AS cs, "
        f"unix_micros(max(_scored_at)) AS scored_at "
        f"FROM {table} WHERE target_date = DATE'{day}'"
    )
    return {
        "target_date": day,
        "rows": row["n"],
        "checksum": row["cs"],
        "scored_at": row["scored_at"],
    }


def _ms(utc: str) -> float:
    return datetime.fromisoformat(utc.replace("Z", "+00:00")).timestamp() * 1000


# ----------------------------------------------------------------------------- AC-76
def test_ac76_full_run_passes_the_pre_check_and_every_task_succeeds_first_time(
    sql, peak_names, peak_job, job, pipeline, peak_runner, evidence
) -> None:
    run = peak_runner.run(peak_job)  # idle state, full daily run, SUCCESS
    by_key = peak_runner.task_runs_by_key(run.run)
    assert set(by_key) == set(DAILY_TASKS)
    for key, runs in by_key.items():
        assert len(runs) == 1, (key, len(runs))
        assert (runs[0].attempt_number or 0) == 0, key  # first time, no retry
        assert _result(runs[0]) == "SUCCESS", key

    pre = by_key["check_pipeline_idle"][0]
    assert _seconds(pre) <= PRE_CHECK_BUDGET_SECONDS, f"pre-check took {_seconds(pre):.0f} s"
    exit_value = run.outputs["check_pipeline_idle"]
    assert exit_value["outcome"] == "idle"
    assert exit_value["ingestion_job"]["job_id"] == job.job_id  # DA-19, A-21
    assert exit_value["ingestion_job"]["active_runs"] == []
    assert exit_value["pipeline"]["pipeline_id"] == pipeline.pipeline_id
    assert exit_value["checked_at"].endswith("Z")

    evidence.save(
        "ac76_run_durations",
        {
            "run_id": run.run.run_id,
            "seconds": (run.run.end_time - run.run.start_time) / 1000,
            "tasks": {key: _seconds(runs[0]) for key, runs in by_key.items()},
        },
    )
    day = run.outputs["score_predictions"]["target_dates"][0]
    evidence.save("ac77_before", _prediction_snapshot(sql, peak_names.predictions, day))


# ----------------------------------------------------------------------------- AC-74
def test_ac74_pre_check_refuses_a_run_while_ingestion_is_active(
    workspace, peak_job, job, peak_runner, evidence
) -> None:
    ingestion_run_id = peak_runner.start_ingestion_run()
    try:
        peak_runner.wait_life_cycle(ingestion_run_id, ("RUNNING",))
        run = peak_runner.run(peak_job, expect="FAILED", require_idle=False)
        by_key = peak_runner.task_runs_by_key(run.run)
        pre = _only_task(peak_runner, run.run, "check_pipeline_idle")
        assert (pre.attempt_number or 0) == 0  # never retried (NFR-23)
        assert _result(pre) == "FAILED"
        assert _seconds(pre) <= PRE_CHECK_BUDGET_SECONDS
        error = run.errors["check_pipeline_idle"]
        assert str(ingestion_run_id) in error
        assert "smart_meter_ingestion" in error
        assert "rerun smart_meter_peak_model" in error
        for key in BLOCKED_TASKS:
            assert _result(by_key[key][0]) == "UPSTREAM_FAILED", key

        # precondition: the ingestion run was still active when the pre-check ended
        current = workspace.jobs.get_run(ingestion_run_id)
        still_active = current.state.life_cycle_state.value not in peak_runner.TERMINAL
        msg = f"ingestion run {ingestion_run_id} ended before the pre-check did: run again"
        assert still_active or (current.end_time or 0) > pre.end_time, msg
    finally:
        ingestion_ended = peak_runner.wait_ended(ingestion_run_id)

    ingestion_tasks = peak_runner.task_runs_by_key(ingestion_ended)
    refresh = (ingestion_tasks.get("refresh_silver_gold") or [None])[0]
    refresh_result = _result(refresh) if refresh is not None else ""
    refresh_ran = refresh_result not in ("", *peak_runner.NEVER_RAN)
    if refresh_ran:
        output = workspace.jobs.get_run_output(refresh.run_id)
        text = f"{output.error or ''} {refresh.state.state_message or ''}"
        assert REFUSAL_TEXT not in text, "the ingestion run's own update was refused"
    upstream = [
        _result(t) for k in ("ingest_files", "ingest_kafka") for t in ingestion_tasks.get(k, [])
    ]
    if upstream and all(r == "SUCCESS" for r in upstream):
        # U-02: with Aiven on, the ingestion run reaches its own refresh and it succeeds
        msg = f"ingestion run {ingestion_run_id}: refresh_silver_gold ended {refresh_result!r}"
        assert refresh_result == "SUCCESS", msg
    evidence.save(
        "ac74_refused_run",
        {
            "ingestion_run_id": ingestion_run_id,
            "ingestion_result": ingestion_ended.state.result_state.value
            if ingestion_ended.state.result_state
            else "",
            "peak_run_id": run.run.run_id,
            "refresh_silver_gold_ran": refresh_ran,
            "refresh_silver_gold_result": refresh_result,
            "ingestion_upstream_results": upstream,
        },
    )


# ----------------------------------------------------------------------------- AC-77
def test_ac77_rerun_after_refusal_succeeds_and_changes_only_scored_at(
    workspace, sql, peak_names, peak_job, peak_runner, evidence
) -> None:
    refused = evidence.load(
        "ac74_refused_run", "test_ac74_pre_check_refuses_a_run_while_ingestion_is_active"
    )
    before = evidence.load(
        "ac77_before", "test_ac76_full_run_passes_the_pre_check_and_every_task_succeeds_first_time"
    )
    ingestion = workspace.jobs.get_run(refused["ingestion_run_id"])
    msg = "ingestion run still active"
    assert ingestion.state.life_cycle_state.value in peak_runner.TERMINAL, msg

    run = peak_runner.run(peak_job)  # the rerun: no other step, expect SUCCESS
    assert _result(_only_task(peak_runner, run.run, "check_pipeline_idle")) == "SUCCESS"
    day = before["target_date"]
    after = _prediction_snapshot(sql, peak_names.predictions, day)
    assert after["rows"] == before["rows"]
    assert after["checksum"] == before["checksum"]  # no column except _scored_at changed
    assert after["scored_at"] > before["scored_at"]


# ----------------------------------------------------------------------------- AC-75
def _wait_pipeline_idle(workspace: Any, job_id: int, pipeline_id: str, minutes: int = 20) -> None:
    deadline = time.monotonic() + minutes * 60
    while not pipeline_guard.check(workspace, job_id, pipeline_id).ok:
        if time.monotonic() > deadline:
            pytest.fail(f"the pipeline was still busy after {minutes} min")
        time.sleep(10)


def test_ac75_pre_check_refuses_a_run_while_a_pipeline_update_is_active(
    workspace, peak_job, job, pipeline, peak_runner
) -> None:
    peak_runner.assert_ingestion_idle()
    update_id = workspace.pipelines.start_update(
        pipeline_id=pipeline.pipeline_id, full_refresh=False
    ).update_id
    try:
        try:
            run = peak_runner.run(
                peak_job,
                only=["check_pipeline_idle", "refresh_silver_gold"],
                expect="FAILED",
                require_idle=False,
            )
        except AssertionError as exc:
            msg = (
                f"{exc}. The update {update_id} may have ended before the pre-check read it "
                "(DA-26); the no-op update lasted about 125 s on dev. Run the test again, and "
                "if it keeps passing vacuously record AC-75 as Partial with a direct "
                "pipeline_guard.check read during the update."
            )
            raise AssertionError(msg) from exc
        pre = _only_task(peak_runner, run.run, "check_pipeline_idle")
        assert (pre.attempt_number or 0) == 0
        assert _result(pre) == "FAILED"
        assert _seconds(pre) <= PRE_CHECK_BUDGET_SECONDS
        error = run.errors["check_pipeline_idle"]
        assert update_id in error
        assert "smart_meter_silver_gold" in error
        refresh = _only_task(peak_runner, run.run, "refresh_silver_gold")
        assert _result(refresh) == "UPSTREAM_FAILED"
    finally:
        _wait_pipeline_idle(workspace, job.job_id, pipeline.pipeline_id)

    # the peak run requested no update of its own: none was created during its lifetime
    updates = workspace.pipelines.list_updates(pipeline.pipeline_id, max_results=5).updates or []
    during = [
        u.update_id
        for u in updates
        if u.update_id != update_id
        and (created := pipeline_guard.utc_text(u.creation_time)) is not None
        and run.run.start_time // 1000 <= _ms(created) // 1000 <= run.run.end_time // 1000
    ]
    assert during == [], f"updates created during the refused run: {during}"
