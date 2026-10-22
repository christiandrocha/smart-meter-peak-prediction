"""Deployed PEAK_MODEL jobs, the single pipeline and the run durations (AC-62).

Prerequisites (evidence for the build report): ``databricks bundle validate -t dev`` and
``databricks bundle deploy -t dev`` from a clean tree (exit codes recorded), then one successful
run of each job (runbook "Bootstrap order" and "Training"). The latest full daily run must include
the pre-check ``check_pipeline_idle``: AC-76 of ``test_peak_concurrency.py`` provides it.

The test starts no run. It checks first that ``smart_meter_ingestion`` and the Silver/Gold pipeline
are idle, so it cannot be confused by (or collide with) a running ingestion job; a pipeline update
requested during that run would be refused and not retried (DA-13, ADR 0008).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
RESOURCES = ROOT / "resources"
DAILY_TASKS = (
    "check_pipeline_idle",
    "refresh_silver_gold",
    "ingest_weather",
    "build_weather_silver",
    "build_features",
    "build_labels",
    "score_predictions",
)
TRAINING_TASKS = ("train_model",)
MAX_DAILY_SECONDS = 7200  # job timeout in the YAML
MAX_TRAINING_SECONDS = 3600


def _yaml_job(file_name: str, key: str) -> dict:
    return yaml.safe_load((RESOURCES / file_name).read_text(encoding="utf-8"))["resources"]["jobs"][
        key
    ]


def _yaml_pipeline() -> dict:
    path = RESOURCES / "smart_meter_silver_gold.pipeline.yml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["resources"]["pipelines"][
        "smart_meter_silver_gold"
    ]


def _task_view(task) -> dict:
    """The comparable fields of a deployed task."""
    return {
        "depends_on": sorted(d.task_key for d in task.depends_on or []),
        "timeout_seconds": task.timeout_seconds,
        "max_retries": task.max_retries or 0,
        "min_retry_interval_millis": task.min_retry_interval_millis or 0,
        # the API omits a boolean left at false, so compare with the default applied
        "disable_auto_optimization": bool(task.disable_auto_optimization),
    }


def _yaml_task_view(task: dict) -> dict:
    return {
        "depends_on": sorted(d["task_key"] for d in task.get("depends_on", [])),
        "timeout_seconds": task.get("timeout_seconds"),
        "max_retries": task.get("max_retries", 0),
        "min_retry_interval_millis": task.get("min_retry_interval_millis", 0),
        "disable_auto_optimization": bool(task.get("disable_auto_optimization", False)),
    }


def _assert_job_matches_yaml(deployed, expected: dict) -> None:
    settings = deployed.settings
    assert settings.max_concurrent_runs == expected.get("max_concurrent_runs", 1)
    assert settings.timeout_seconds == expected["timeout_seconds"]
    if "schedule" in expected:
        assert settings.schedule is not None
        assert (
            settings.schedule.quartz_cron_expression
            == expected["schedule"]["quartz_cron_expression"]
        )
        assert settings.schedule.timezone_id == expected["schedule"]["timezone_id"]
    else:
        assert settings.schedule is None
        assert settings.trigger is None
    deployed_tasks = {t.task_key: _task_view(t) for t in settings.tasks}
    yaml_tasks = {t["task_key"]: _yaml_task_view(t) for t in expected["tasks"]}
    assert deployed_tasks == yaml_tasks
    if "parameters" in expected:
        deployed_parameters = {p.name: p.default for p in settings.parameters or []}
        assert deployed_parameters == {p["name"]: p["default"] for p in expected["parameters"]}


def _latest_success(workspace, job, task_keys: tuple[str, ...]):
    """Newest run in which every listed task succeeded and the run had no quota termination."""
    runs = workspace.jobs.list_runs(
        job_id=job.job_id, completed_only=True, expand_tasks=True, limit=25
    )
    for run in sorted(runs, key=lambda r: r.start_time, reverse=True):
        done = {
            t.task_key
            for t in run.tasks or []
            if t.state and t.state.result_state and t.state.result_state.value == "SUCCESS"
        }
        if (
            run.state.result_state
            and run.state.result_state.value == "SUCCESS"
            and (set(task_keys) <= done)
        ):
            return workspace.jobs.get_run(run.run_id)
    return None


def test_ac62_deployed_jobs_pipeline_and_run_durations(
    workspace, job, pipeline, peak_job, training_job, peak_runner, evidence, strip_dev_prefix
) -> None:
    peak_runner.assert_ingestion_idle()

    # both PEAK_MODEL jobs exist by base name with the YAML settings
    _assert_job_matches_yaml(
        peak_job, _yaml_job("smart_meter_peak_model.job.yml", "smart_meter_peak_model")
    )
    _assert_job_matches_yaml(
        training_job,
        _yaml_job("smart_meter_peak_model_training.job.yml", "smart_meter_peak_model_training"),
    )
    assert {t.task_key for t in peak_job.settings.tasks} == set(DAILY_TASKS)
    assert {t.task_key for t in training_job.settings.tasks} == set(TRAINING_TASKS)
    assert training_job.settings.schedule is None  # on demand only (D-36)

    # DA-19: the bundle references resolved to the ids of the deployed objects (AC-68)
    (pre_check,) = (t for t in peak_job.settings.tasks if t.task_key == "check_pipeline_idle")
    ids = pre_check.notebook_task.base_parameters
    assert ids["ingestion_job_id"] == str(job.job_id)
    assert ids["pipeline_id"] == pipeline.pipeline_id

    # exactly one pipeline in the bundle, and the METER_INGESTION objects equal their YAML
    names = [strip_dev_prefix(p.name or "") for p in workspace.pipelines.list_pipelines()]
    assert names.count("smart_meter_silver_gold") == 1
    deployed = workspace.pipelines.get(pipeline.pipeline_id).spec
    expected = _yaml_pipeline()
    # the API omits a boolean left at its default (false), so compare with the default applied
    assert bool(deployed.serverless) is expected["serverless"]
    assert bool(deployed.continuous) is expected["continuous"]
    assert deployed.channel == expected["channel"]
    assert deployed.configuration["spark.sql.session.timeZone"] == "UTC"
    _assert_job_matches_yaml(
        job, _yaml_job("smart_meter_ingestion.job.yml", "smart_meter_ingestion")
    )

    # the latest successful runs: no quota termination, durations saved as evidence
    durations = {}
    for label, target, tasks, budget in (
        ("daily", peak_job, DAILY_TASKS, MAX_DAILY_SECONDS),
        ("training", training_job, TRAINING_TASKS, MAX_TRAINING_SECONDS),
    ):
        run = _latest_success(workspace, target, tasks)
        assert run is not None, f"no successful {label} run: run the job (runbook)"
        assert run.status.termination_details.code.value == "SUCCESS"  # no quota termination
        seconds = (run.end_time - run.start_time) / 1000
        assert seconds <= budget, f"the {label} run took {seconds:.0f} s"
        durations[label] = {
            "run_id": run.run_id,
            "seconds": seconds,
            "tasks": {t.task_key: (t.end_time - t.start_time) / 1000 for t in run.tasks},
        }
    evidence.save("ac62_peak_run_durations", durations)
