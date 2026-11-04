"""Reverse pre-check of the ingestion job on dev (AC-94 to AC-98, AC-106; ADR 0013).

Run order (runbook "Evidence order", and the DESIGN): AC-94 first, right after
``databricks bundle deploy -t dev`` from a clean tree; then AC-97 (it needs no Kafka); then the
Kafka block ordered by the current Aiven state (AC-96, then the AC-28 and AC-30 tests of
``test_deployment.py``, then the PEAK_MODEL_CONCURRENCY suite and AC-98, then AC-95 in
``test_bronze_ingestion.py``). AC-96 starts one full ingestion run that the METER_INGESTION AC-30
test reuses. AC-97 starts one no-op pipeline update and two subset runs; the busy-case run uses
``require_idle=False`` because the busy state is what it tests.

AC97_TIMING_EVIDENCE: AC-97 also writes ``out/evidence/ac97_timing.json`` (also when it fails),
and AC-106 reads that file back and cross-checks it with the platform without starting anything.
Order: AC-97, then AC-106 right after. The pure helpers are ``tests/support/ac97_timing.py``.
"""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime
from itertools import islice
from pathlib import Path
from typing import Any

import pytest
import yaml
from support import ac97_timing

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


def _wait_pipeline_idle(
    workspace: Any,
    pipeline_id: str,
    minutes: int = 20,
    watch: ac97_timing.UpdateWatch | None = None,
) -> None:
    deadline = time.monotonic() + minutes * 60
    while True:
        pipeline = workspace.pipelines.get(pipeline_id)
        if watch is not None:
            _observe(pipeline, watch)
        state = pipeline.state
        if state is not None and state.value == "IDLE":  # exactly IDLE, as assert_ingestion_idle
            return
        if time.monotonic() > deadline:
            raise AssertionError(f"the pipeline was still not IDLE after {minutes} min")
        time.sleep(10)


def _enum(value: Any) -> str | None:
    inner = getattr(value, "value", value)
    return None if inner is None else str(inner)


def _observe(pipeline: Any, watch: ac97_timing.UpdateWatch) -> None:
    """Record U's creation time and state from ``latest_updates``; first terminal poll time."""
    for entry in getattr(pipeline, "latest_updates", None) or []:
        if getattr(entry, "update_id", None) != watch.update_id:
            continue
        if watch.created is None:
            watch.created = getattr(entry, "creation_time", None)
        state = _enum(getattr(entry, "state", None))
        watch.state = state
        if state in pipeline_guard.TERMINAL_UPDATE_STATES and watch.observed_terminal_ts is None:
            watch.observed_terminal_ts = pipeline_guard.utc_text(datetime.now(UTC))


# ----------------------------------------------------------------------------- AC-97 evidence
def _skipped(what: str, exc: Exception) -> None:
    """G-33: one line with the class and the error code only, never the message body."""
    code = getattr(exc, "error_code", None)
    print(f"AC-97 timing evidence: {what} not read ({type(exc).__name__} {code or '-'})")


def _check_output(workspace: Any, task: Any, facts: ac97_timing.Ac97Facts) -> None:
    output = workspace.jobs.get_run_output(task.run_id)
    if output.error:
        facts.check_error = f"{output.error} {output.error_trace or ''}"
    if output.notebook_output and output.notebook_output.result:
        facts.check_exit = json.loads(output.notebook_output.result)


def _task_facts(run: Any) -> ac97_timing.TaskFacts:
    tasks = [t for t in run.tasks or [] if t.task_key == CHECK]
    task = tasks[0] if tasks else None
    return ac97_timing.TaskFacts(
        run_id=run.run_id,
        task_run_id=getattr(task, "run_id", None),
        start=getattr(task, "start_time", None),
        end=getattr(task, "end_time", None),
        result=_result(task) or None if task is not None else None,
    )


def _capture_found_run(
    workspace: Any, job: Any, before_ms: int, facts: ac97_timing.Ac97Facts
) -> None:
    """Failure path: the refused run was not returned, so find it (2 reads, guarded)."""
    try:
        listed = workspace.jobs.list_runs(
            job_id=job.job_id, start_time_from=before_ms, expand_tasks=True, limit=5
        )
        runs = list(islice(listed, 5))
        if not runs:
            return
        run = min(runs, key=lambda r: r.start_time or 0)  # the oldest one after the update
        facts.refused = _task_facts(run)
        if facts.refused.task_run_id is not None:
            task = next(t for t in run.tasks if t.task_key == CHECK)
            _check_output(workspace, task, facts)
    except Exception as exc:  # noqa: BLE001 - the evidence never masks the AC-97 result (G-33)
        _skipped("the refused run", exc)


def _capture_refused(refused: Any, facts: ac97_timing.Ac97Facts) -> None:
    """The run that AC-97 asserts on, already read by the runner: no platform call."""
    try:
        facts.refused = _task_facts(refused.run)
        facts.check_error = refused.errors.get(CHECK)
        facts.check_exit = refused.outputs.get(CHECK)
    except Exception as exc:  # noqa: BLE001 - never hides the AC-97 asserts that follow (G-33)
        _skipped("the refused run", exc)


def _capture_rerun(rerun: Any, facts: ac97_timing.Ac97Facts) -> None:
    try:
        facts.rerun_run_id = rerun.run.run_id
        facts.rerun_check_result = _first_result(rerun.run, CHECK)
        facts.rerun_refresh_result = _first_result(rerun.run, REFRESH)
    except Exception as exc:  # noqa: BLE001
        _skipped("the rerun", exc)


def _first_result(run: Any, key: str) -> str | None:
    found = [t for t in run.tasks or [] if t.task_key == key]
    return (_result(found[0]) or None) if found else None


def _read_update_end(workspace: Any, pipeline_id: str, facts: ac97_timing.Ac97Facts) -> None:
    """U's creation time, final state and the newest event page (2 reads, guarded)."""
    facts.end_read = True
    try:
        update = workspace.pipelines.get_update(pipeline_id, facts.update_id).update
        facts.update_created = getattr(update, "creation_time", None)
        facts.update_state = _enum(getattr(update, "state", None))
    except Exception as exc:  # noqa: BLE001
        _skipped("the update", exc)
    try:
        events = workspace.pipelines.list_pipeline_events(pipeline_id, max_results=50)
        facts.events = [event.as_dict() for event in islice(events, 50)]
    except Exception as exc:  # noqa: BLE001
        _skipped("the pipeline events", exc)


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
    workspace, job, peak_job, pipeline, peak_runner, evidence
) -> None:
    peak_runner.assert_ingestion_idle()
    _assert_peak_job_idle(workspace, peak_job)
    subset = [CHECK, REFRESH]
    before_ms = int(time.time() * 1000) - START_SLACK_SECONDS * 1000
    update_id = workspace.pipelines.start_update(
        pipeline_id=pipeline.pipeline_id, full_refresh=False
    ).update_id
    facts = ac97_timing.Ac97Facts(update_id, ac97_timing.UpdateWatch(update_id))
    try:
        try:
            try:
                refused = peak_runner.run(job, only=subset, expect="FAILED", require_idle=False)
            except AssertionError as exc:
                _capture_found_run(workspace, job, before_ms, facts)
                msg = f"{exc}. {ac97_timing.failure_hint(update_id)}"
                raise AssertionError(msg) from exc
            _capture_refused(refused, facts)
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
            _wait_pipeline_idle(workspace, pipeline.pipeline_id, watch=facts.watch)
        _read_update_end(workspace, pipeline.pipeline_id, facts)

        # the refused run requested no update of its own: none but U was created during its life
        during = [
            u.update_id
            for u in _updates_between(
                workspace, pipeline.pipeline_id, refused.run.start_time, refused.run.end_time
            )
            if u.update_id != update_id
        ]
        assert during == [], f"updates created during the refused run: {during}"

        rerun = peak_runner.run(job, only=subset, require_idle=True)  # expect SUCCESS
        _capture_rerun(rerun, facts)
        assert _result(_one(peak_runner, rerun.run, CHECK)) == "SUCCESS"
        assert _result(_one(peak_runner, rerun.run, REFRESH)) == "SUCCESS"
        assert rerun.outputs[CHECK]["outcome"] == "idle"
    except BaseException as exc:  # noqa: BLE001 - names the evidence file on any failure (FR-58)
        exc.add_note(ac97_timing.EVIDENCE_NOTE)
        print(ac97_timing.EVIDENCE_NOTE)
        raise
    finally:
        if not facts.end_read:
            _read_update_end(workspace, pipeline.pipeline_id, facts)
        try:
            evidence.save(ac97_timing.EVIDENCE_NAME, ac97_timing.build_record(facts))
        except Exception as exc:  # noqa: BLE001 - never replaces the AC-97 result (G-33)
            _skipped("the evidence file", exc)


# ----------------------------------------------------------------------------- AC-106
def _seconds_of(utc: str) -> float:
    return _ms(utc) / 1000


def _update_creation_ms(workspace: Any, pipeline_id: str, update_id: str) -> int:
    """Creation time of U; DA-36 fallback: the update list when ``get_update`` cannot read it."""
    try:
        return workspace.pipelines.get_update(pipeline_id, update_id).update.creation_time
    except Exception as exc:  # noqa: BLE001
        _skipped("the update (AC-106)", exc)
    listed = workspace.pipelines.list_updates(pipeline_id, max_results=25).updates or []
    found = [u.creation_time for u in listed if u.update_id == update_id]
    assert found, f"update {update_id} is not listed for the pipeline"
    return found[0]


def test_ac106_ac97_timing_evidence_matches_the_platform(
    workspace, job, pipeline, evidence
) -> None:
    """Right after AC-97: the saved timing is consistent and agrees with the platform (3 reads)."""
    ac97 = "test_ac97_check_refuses_while_an_update_is_active_and_the_rerun_succeeds"
    record = evidence.load(ac97_timing.EVIDENCE_NAME, ac97)
    assert set(record) == {*ac97_timing.RECORD_FIELDS, "saved_at_ms"}
    assert record["outcome"] == "refused", record
    assert record["check_read_update_state"] not in pipeline_guard.TERMINAL_UPDATE_STATES
    assert record["check_read_update_state"] is not None
    required = (
        "update_created_ts", "check_read_ts", "check_started_ts", "check_ended_ts",
        "update_ended_ts", "update_outlived_read_seconds", "read_after_creation_seconds",
        "update_end_source", "refused_run_id", "rerun_run_id",
    )  # fmt: skip
    missing = [key for key in required if record[key] is None]
    assert not missing, f"AC-97 evidence has null fields {missing}: {record}"
    created, read = record["update_created_ts"], record["check_read_ts"]
    started, ended = record["check_started_ts"], record["check_ended_ts"]
    assert created <= read, f"read {read} before creation {created}"
    assert _seconds_of(started) - 1 <= _seconds_of(read) <= _seconds_of(ended) + 1
    margin = ac97_timing.margins(created, read, record["update_ended_ts"])
    assert record["update_outlived_read_seconds"] > 0
    assert record["read_after_creation_seconds"] >= 0
    assert record["update_outlived_read_seconds"] == margin["update_outlived_read_seconds"]
    assert record["read_after_creation_seconds"] == margin["read_after_creation_seconds"]
    assert record["update_end_source"] in ac97_timing.END_SOURCES
    assert record["refused_run_id"] != record["rerun_run_id"]

    refused = workspace.jobs.get_run(record["refused_run_id"])
    rerun = workspace.jobs.get_run(record["rerun_run_id"])
    assert refused.job_id == job.job_id
    assert rerun.job_id == job.job_id
    assert refused.start_time >= _ms(created) - 5000, "the refused run started before the update"
    assert rerun.start_time > refused.end_time, "the rerun did not start after the refused run"
    creation_ms = _update_creation_ms(workspace, pipeline.pipeline_id, record["update_id"])
    assert pipeline_guard.utc_text(creation_ms) == created
    assert record["saved_at_ms"] > creation_ms
    age_ms = int(time.time() * 1000) - record["saved_at_ms"]
    assert age_ms < 30 * 60 * 1000, f"the evidence file is {age_ms // 60000} min old: rerun AC-97"
    print(f"AC-106 evidence: {json.dumps(record, sort_keys=True)}")


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
