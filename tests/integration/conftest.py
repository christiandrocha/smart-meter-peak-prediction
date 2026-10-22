"""Fixtures for the integration tests against the deployed ``dev`` environment (manifest 53).

These tests need a live workspace, a SQL warehouse and, for the Kafka checks, the Aiven service.
They carry the ``integration`` marker and are excluded from the default ``pytest`` run and from CI
(``addopts`` in ``pyproject.toml``). Run them in the order of the runbook
(``docs/runbooks/meter_ingestion.md``)::

    pip install -e ".[dev,integration]"
    export DATABRICKS_CONFIG_PROFILE=dev          # CLI profile; or DATABRICKS_HOST + OAuth env
    pytest -m integration tests/integration/<file>

Credentials come from the Databricks CLI profile or the standard ``DATABRICKS_*`` environment
variables, never from files in the repository. The SDK is imported lazily, so merely collecting
these modules needs no workspace and no ``databricks-sdk``.

Settings overrides (optional): ``SMART_METER_<FIELD>`` for any ``Settings`` field, for example
``SMART_METER_CATALOG=workspace`` for the A-09 fallback layout. ``DATABRICKS_WAREHOUSE_ID`` selects
the SQL warehouse (default: the first one the workspace lists). ``SAMPLE_MANIFEST`` is the path of
the extended ``manifest.json`` written by ``scripts/prepare_sample.py build`` (default
``data/sample/seed42/manifest.json``).

Time is UTC end to end: the fixtures fail when the warehouse session time zone is not UTC.
Snapshots for before/after tests are JSON files in ``out/evidence/`` (git-ignored).

PEAK_MODEL (manifest 36 to 40) adds fixtures for its two jobs (found by base name), a runner that
starts them with job parameters and ``only=`` and reads the task exit values, the MLflow client and
artifact download, and registry reads. ``mlflow`` is imported lazily, so collecting needs neither
it nor the SDK. The runbook is ``docs/runbooks/peak_model.md``.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, fields
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from smart_meter_peak_prediction import metrics, peak_config, pipeline_guard
from smart_meter_peak_prediction.config import Settings
from smart_meter_peak_prediction.rules import DROP_RULE_PRECEDENCE

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "out" / "evidence"
CONFIG_MANIFEST = ROOT / "config" / "sample_manifest.json"
DEFAULT_SAMPLE_MANIFEST = ROOT / "data" / "sample" / "seed42" / "manifest.json"
CONTRACTS_DIR = ROOT / "docs" / "contracts"

JOB_NAME = "smart_meter_ingestion"
PIPELINE_NAME = "smart_meter_silver_gold"
PEAK_JOB_NAME = "smart_meter_peak_model"
TRAINING_JOB_NAME = "smart_meter_peak_model_training"
DEV_PREFIX = re.compile(r"^\[dev [^\]]+\] ")  # development-mode display prefix (AC-28)

STATEMENT_TIMEOUT_S = 900
_INT_TYPES = {"BYTE", "SHORT", "INT", "LONG"}
_FLOAT_TYPES = {"FLOAT", "DOUBLE"}


def strip_dev_prefix(name: str) -> str:
    return DEV_PREFIX.sub("", name, count=1)


# ----------------------------------------------------------------------------- workspace
@pytest.fixture(scope="session")
def workspace() -> Any:
    try:
        from databricks.sdk import WorkspaceClient
    except ImportError:
        pytest.fail("databricks-sdk is missing; install it with: pip install -e '.[integration]'")
    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE")
    return WorkspaceClient(profile=profile) if profile else WorkspaceClient()


@pytest.fixture(scope="session")
def settings() -> Settings:
    overrides = {
        field.name: os.environ[f"SMART_METER_{field.name.upper()}"]
        for field in fields(Settings)
        if os.environ.get(f"SMART_METER_{field.name.upper()}")
    }
    return Settings.from_mapping(overrides)


class Sql:
    """SQL through the Statement Execution API on the Free Edition warehouse."""

    def __init__(self, client: Any, warehouse_id: str) -> None:
        self.client = client
        self.warehouse_id = warehouse_id

    def rows(self, statement: str) -> list[dict[str, Any]]:
        from databricks.sdk.service.sql import StatementState

        api = self.client.statement_execution
        response = api.execute_statement(
            statement=statement, warehouse_id=self.warehouse_id, wait_timeout="50s"
        )
        deadline = time.monotonic() + STATEMENT_TIMEOUT_S
        while response.status.state in (StatementState.PENDING, StatementState.RUNNING):
            if time.monotonic() > deadline:
                api.cancel_execution(response.statement_id)
                raise AssertionError(f"SQL statement timed out:\n{statement[:600]}")
            time.sleep(3)
            response = api.get_statement(response.statement_id)
        if response.status.state != StatementState.SUCCEEDED:
            error = response.status.error.message if response.status.error else "no message"
            raise AssertionError(f"SQL statement failed ({error}):\n{statement[:600]}")

        columns = [
            (col.name, col.type_name.value if col.type_name else "STRING")
            for col in response.manifest.schema.columns
        ]
        data = list(response.result.data_array or []) if response.result else []
        chunk = response.result.next_chunk_index if response.result else None
        while chunk is not None:
            part = api.get_statement_result_chunk_n(response.statement_id, chunk)
            data.extend(part.data_array or [])
            chunk = part.next_chunk_index
        return [
            {
                name: _convert(value, type_name)
                for (name, type_name), value in zip(columns, row, strict=True)
            }
            for row in data
        ]

    def one(self, statement: str) -> dict[str, Any]:
        result = self.rows(statement)
        assert len(result) == 1, f"expected one row, got {len(result)}:\n{statement[:600]}"
        return result[0]

    def scalar(self, statement: str) -> Any:
        return next(iter(self.one(statement).values()))


def _convert(value: str | None, type_name: str) -> Any:
    if value is None:
        return None
    if type_name in _INT_TYPES:
        return int(value)
    if type_name in _FLOAT_TYPES:
        return float(value)
    if type_name == "DECIMAL":
        return Decimal(value)
    if type_name == "BOOLEAN":
        return value.lower() == "true"
    return value


@pytest.fixture(scope="session")
def sql(workspace: Any) -> Sql:
    warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID", "").strip()
    if not warehouse_id:
        warehouses = list(workspace.warehouses.list())
        assert warehouses, "no SQL warehouse found; set DATABRICKS_WAREHOUSE_ID"
        warehouse_id = warehouses[0].id
    runner = Sql(workspace, warehouse_id)
    zone = runner.scalar("SELECT current_timezone()")
    assert zone in ("UTC", "Etc/UTC", "GMT"), (
        f"the warehouse session time zone is {zone}; set the SQL configuration parameter "
        "TIMEZONE to UTC in the workspace SQL settings (golden rule 5)"
    )
    return runner


# ----------------------------------------------------------------------------- bundle objects
@pytest.fixture(scope="session", name="strip_dev_prefix")
def strip_dev_prefix_fixture() -> Callable[[str], str]:
    return strip_dev_prefix


def _only(matches: list[Any], what: str) -> Any:
    assert len(matches) == 1, f"expected exactly one {what}, found {len(matches)}"
    return matches[0]


@pytest.fixture(scope="session")
def job(workspace: Any) -> Any:
    found = [
        j
        for j in workspace.jobs.list(expand_tasks=True)
        if j.settings and strip_dev_prefix(j.settings.name or "") == JOB_NAME
    ]
    return _only(found, f"job named {JOB_NAME} (development prefix stripped)")


@pytest.fixture(scope="session")
def pipeline(workspace: Any) -> Any:
    found = [
        p
        for p in workspace.pipelines.list_pipelines()
        if strip_dev_prefix(p.name or "") == PIPELINE_NAME
    ]
    return _only(found, f"pipeline named {PIPELINE_NAME} (development prefix stripped)")


@pytest.fixture
def full_runs(workspace: Any, job: Any) -> Callable[[], list[Any]]:
    """Successful runs of all four tasks, newest first (partial ``only=`` runs are excluded)."""
    all_tasks = {t.task_key for t in job.settings.tasks}

    def find() -> list[Any]:
        runs = workspace.jobs.list_runs(
            job_id=job.job_id, completed_only=True, expand_tasks=True, limit=25
        )
        full = [
            r
            for r in runs
            if r.state
            and r.state.result_state
            and r.state.result_state.value == "SUCCESS"
            and {t.task_key for t in r.tasks or []} == all_tasks
            # an `only=` run still lists every task; the ones it skips end DISABLED
            and all(
                t.state and t.state.result_state and t.state.result_state.value == "SUCCESS"
                for t in r.tasks
            )
        ]
        return sorted(full, key=lambda r: r.start_time, reverse=True)

    return find


@pytest.fixture
def run_tasks(workspace: Any, job: Any) -> Callable[[list[str]], Any]:
    """Run only the named tasks of the daily job and wait; fail unless the run succeeds."""

    def run(task_keys: list[str]) -> Any:
        waiter = workspace.jobs.run_now(job_id=job.job_id, only=task_keys)
        result = waiter.result(timeout=timedelta(minutes=50))
        state = (
            result.state.result_state.value if result.state and result.state.result_state else ""
        )
        assert state == "SUCCESS", f"run of {task_keys} ended with {state}: {result.run_page_url}"
        return result

    return run


# ----------------------------------------------------------------------------- reference data
@pytest.fixture(scope="session")
def config_manifest() -> dict[str, Any]:
    """Pinned seed-42 counts and checksums (``config/sample_manifest.json``)."""
    return json.loads(CONFIG_MANIFEST.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def sample_manifest() -> dict[str, Any]:
    """Extended manifest written by ``scripts/prepare_sample.py build`` (per-household facts)."""
    path = Path(os.environ.get("SAMPLE_MANIFEST", str(DEFAULT_SAMPLE_MANIFEST)))
    if not path.is_file():
        pytest.fail(
            f"{path} not found: run `python scripts/prepare_sample.py build --out "
            "data/sample/seed42` or set SAMPLE_MANIFEST"
        )
    return json.loads(path.read_text(encoding="utf-8"))


class Contracts:
    """Data contracts in ``docs/contracts`` mapped to the deployed layout."""

    def load(self, stem: str) -> dict[str, Any]:
        return yaml.safe_load((CONTRACTS_DIR / f"{stem}.yaml").read_text(encoding="utf-8"))

    def columns(self, stem: str) -> list[tuple[str, str]]:
        return [(c["name"], c["type"].lower()) for c in self.load(stem)["schema"]]

    def table(self, stem: str, settings: Settings) -> str:
        """Fully qualified name in the configured layout (main or A-09 fallback)."""
        _, layer, name = self.load(stem)["dataset"].split(".")
        return settings.table(layer, name)


@pytest.fixture(scope="session")
def contracts() -> Contracts:
    return Contracts()


@pytest.fixture(scope="session")
def checksum(sql: Sql) -> Callable[[str, list[str]], dict[str, Any]]:
    """Order-independent row count and checksum of a table (``metrics.table_checksum_sql``)."""

    def compute(table: str, columns: list[str]) -> dict[str, Any]:
        row = sql.one(metrics.table_checksum_sql(table, columns))
        return {"row_count": row["row_count"], "checksum": str(row["checksum"])}

    return compute


# ----------------------------------------------------------------------------- evidence
class Evidence:
    """JSON snapshots for the ``*_before`` and ``*_after`` test pairs."""

    def save(self, name: str, data: dict[str, Any]) -> None:
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {"saved_at_ms": int(time.time() * 1000), **data}
        (EVIDENCE_DIR / f"{name}.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )

    def load(self, name: str, before_test: str) -> dict[str, Any]:
        path = EVIDENCE_DIR / f"{name}.json"
        if not path.is_file():
            pytest.fail(f"snapshot {path.name} is missing: run {before_test} first (see runbook)")
        return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def evidence() -> Evidence:
    return Evidence()


# ----------------------------------------------------------------------------- shared checks
@pytest.fixture(scope="session")
def assert_rule_totals_consistent(sql: Sql, settings: Settings) -> Callable[[], dict[str, Any]]:
    """AC-12: the table totals of ``metrics.py`` agree with Bronze, quarantine and Silver.

    Totals are table state, not per-update deltas (DA-01 fallback), so the check holds at any time
    after an update and after a full refresh.
    """

    def check() -> dict[str, Any]:
        evaluated = settings.table("silver", "meter_readings_evaluated")
        quarantine = settings.table("silver", "meter_readings_quarantine")
        silver = settings.table("silver", "meter_readings")
        totals = sql.one(metrics.rule_counts_sql(evaluated))
        bronze = sql.scalar(
            f"SELECT (SELECT count(*) FROM {settings.bronze_files_readings}) "
            f"+ (SELECT count(*) FROM {settings.bronze_kafka_readings})"
        )
        assert totals["evaluated_rows"] == bronze
        per_rule = {
            row["rule"]: row["n"]
            for row in sql.rows(
                "SELECT rule, count(*) AS n FROM "
                f"(SELECT explode(failed_rules) AS rule FROM {quarantine}) GROUP BY rule"
            )
        }
        for rule in sorted(DROP_RULE_PRECEDENCE):
            assert totals[metrics.count_column(rule)] == per_rule.get(rule, 0), rule
        assert totals["quarantine_rows"] == sql.scalar(f"SELECT count(*) FROM {quarantine}")
        assert totals["silver_rows"] == sql.scalar(f"SELECT count(*) FROM {silver}")
        # QR-09 b: a dropped record appears once in the quarantine; its repeats are counted
        # only in the duplicate total (and are not in any per-rule total)
        assert sql.scalar(f"SELECT count(*) - count(DISTINCT _dedup_key) FROM {quarantine}") == 0
        valid_duplicates = sql.scalar(
            f"SELECT count_if(is_duplicate AND NOT is_quarantine_duplicate) FROM {evaluated}"
        )
        assert totals["qr_09"] == valid_duplicates + totals["quarantine_duplicates"]
        assert totals["sf_01"] >= 0
        return totals

    return check


# ----------------------------------------------------------------------------- PEAK_MODEL jobs
def _job_named(workspace: Any, name: str) -> Any:
    found = [
        j
        for j in workspace.jobs.list(expand_tasks=True)
        if j.settings and strip_dev_prefix(j.settings.name or "") == name
    ]
    listed = _only(found, f"job named {name} (development prefix stripped)")
    # jobs.list returns abbreviated settings without the job parameters; read the full job
    return workspace.jobs.get(listed.job_id)


@pytest.fixture(scope="session")
def peak_job(workspace: Any) -> Any:
    """The daily job ``smart_meter_peak_model``, by base name."""
    return _job_named(workspace, PEAK_JOB_NAME)


@pytest.fixture(scope="session")
def training_job(workspace: Any) -> Any:
    """The on-demand job ``smart_meter_peak_model_training``, by base name."""
    return _job_named(workspace, TRAINING_JOB_NAME)


@dataclass
class PeakRun:
    """A finished job run: its state and the parsed notebook exit value of every task."""

    run: Any
    outputs: dict[str, dict[str, Any]]
    errors: dict[str, str]

    @property
    def result_state(self) -> str:
        state = self.run.state
        return state.result_state.value if state and state.result_state else ""

    @property
    def url(self) -> str:
        return self.run.run_page_url or ""


class PeakRunner:
    """Start a PEAK_MODEL job with job parameters and ``only=`` and wait for it to end.

    Every run first checks that the ingestion job and the pipeline are idle, with the same
    ``pipeline_guard.check`` as the daily job's pre-check (one definition of "active", ADR 0012),
    unless ``require_idle=False`` (the busy-case tests of PEAK_MODEL_CONCURRENCY). A pipeline
    update requested while the ingestion job runs is refused and the task ends INTERNAL_ERROR
    without a retry (DA-13), and the other tasks read Gold, which must be stable.
    """

    TERMINAL = tuple(sorted(pipeline_guard.TERMINAL_RUN_STATES))
    NEVER_RAN = ("DISABLED", "UPSTREAM_FAILED", "UPSTREAM_CANCELED")

    def __init__(self, client: Any, ingestion_job_id: int, pipeline_id: str) -> None:
        self.client = client
        self.ingestion_job_id = ingestion_job_id
        self.pipeline_id = pipeline_id

    def assert_ingestion_idle(self) -> None:
        report = pipeline_guard.check(self.client, self.ingestion_job_id, self.pipeline_id)
        msg = "the shared pipeline is not idle (DA-13); wait and run again:\n" + report.message()
        assert report.ok, msg
        state = self.client.pipelines.get(self.pipeline_id).state
        status = state.value if state else "IDLE"
        assert status == "IDLE", f"pipeline smart_meter_silver_gold is {status}, not IDLE"

    def run(
        self,
        job: Any,
        *,
        params: dict[str, str] | None = None,
        only: list[str] | None = None,
        expect: str = "SUCCESS",
        timeout: timedelta = timedelta(minutes=60),
        require_idle: bool = True,
    ) -> PeakRun:
        tasks = {t.task_key for t in job.settings.tasks}
        assert set(only or []) <= tasks, f"unknown task in only={only}"
        if require_idle:
            self.assert_ingestion_idle()  # also without the pipeline task: Gold must be stable
        kwargs: dict[str, Any] = {"job_id": job.job_id}
        if params:
            kwargs["job_parameters"] = params
        if only is not None:
            kwargs["only"] = only
        run_id = self.client.jobs.run_now(**kwargs).run_id
        deadline = time.monotonic() + timeout.total_seconds()
        run = self.client.jobs.get_run(run_id)
        while run.state.life_cycle_state.value not in self.TERMINAL:
            if time.monotonic() > deadline:
                self.client.jobs.cancel_run(run_id)
                pytest.fail(f"run {run_id} did not end in {timeout}; cancelled")
            time.sleep(15)
            run = self.client.jobs.get_run(run_id)
        result = run.state.result_state.value if run.state.result_state else ""
        ended = f"run of {only or 'all tasks'} ended {result!r}: {run.run_page_url}"
        assert result == expect, ended
        outputs: dict[str, dict[str, Any]] = {}
        errors: dict[str, str] = {}
        for task in run.tasks or []:
            if not task.state or not task.state.result_state:
                continue
            if task.state.result_state.value in self.NEVER_RAN or (
                only is not None and task.task_key not in only
            ):
                continue
            output = self.client.jobs.get_run_output(task.run_id)
            if output.notebook_output and output.notebook_output.result:
                outputs[task.task_key] = json.loads(output.notebook_output.result)
            if output.error:
                errors[task.task_key] = f"{output.error} {output.error_trace or ''}"
        return PeakRun(run=run, outputs=outputs, errors=errors)

    # ------------------------------------------------------------------ concurrency helpers
    def start_ingestion_run(self) -> int:
        """Start ``smart_meter_ingestion`` from an idle state and return its run id."""
        self.assert_ingestion_idle()
        return self.client.jobs.run_now(job_id=self.ingestion_job_id).run_id

    def wait_life_cycle(
        self, run_id: int, states: tuple[str, ...], timeout: timedelta = timedelta(minutes=20)
    ) -> Any:
        """Poll a run until its life-cycle state is one of ``states``; fail if it ended first."""
        deadline = time.monotonic() + timeout.total_seconds()
        while True:
            run = self.client.jobs.get_run(run_id)
            state = run.state.life_cycle_state.value
            if state in states:
                return run
            if state in self.TERMINAL:
                pytest.fail(f"run {run_id} ended ({state}) before reaching {states}")
            if time.monotonic() > deadline:
                pytest.fail(f"run {run_id} did not reach {states} in {timeout}")
            time.sleep(5)

    def wait_ended(self, run_id: int, timeout: timedelta = timedelta(minutes=60)) -> Any:
        """Poll a run until it is over and return it."""
        deadline = time.monotonic() + timeout.total_seconds()
        while True:
            run = self.client.jobs.get_run(run_id)
            if run.state.life_cycle_state.value in self.TERMINAL:
                return run
            if time.monotonic() > deadline:
                pytest.fail(f"run {run_id} did not end in {timeout}")
            time.sleep(15)

    @staticmethod
    def task_runs_by_key(run: Any) -> dict[str, list[Any]]:
        """Task runs of a job run grouped by task key (more than one entry means a retry)."""
        grouped: dict[str, list[Any]] = {}
        for task in run.tasks or []:
            grouped.setdefault(task.task_key, []).append(task)
        return grouped


@pytest.fixture(scope="session")
def peak_runner(workspace: Any, job: Any, pipeline: Any) -> PeakRunner:
    return PeakRunner(workspace, job.job_id, pipeline.pipeline_id)


@dataclass
class PeakNames:
    model: str
    features: str
    labels: str
    predictions: str
    bronze_weather: str
    silver_weather: str
    experiment: str


@pytest.fixture(scope="session")
def peak_names(workspace: Any, settings: Settings) -> PeakNames:
    user = workspace.current_user.me().user_name
    return PeakNames(
        model=peak_config.model_name(settings),
        features=peak_config.features_table(settings),
        labels=peak_config.labels_table(settings),
        predictions=peak_config.predictions_table(settings),
        bronze_weather=peak_config.bronze_weather_table(settings),
        silver_weather=peak_config.silver_weather_table(settings),
        experiment=peak_config.experiment_path(user),
    )


# ----------------------------------------------------------------------------- MLflow
class Mlflow:
    """MLflow tracking and the UC registry of the workspace, read-only helpers for the tests."""

    def __init__(self, names: PeakNames) -> None:
        import mlflow
        from mlflow import MlflowClient

        mlflow.set_tracking_uri("databricks")
        mlflow.set_registry_uri("databricks-uc")
        self.mlflow = mlflow
        self.client = MlflowClient()
        self.names = names
        self._scratch = tempfile.TemporaryDirectory(prefix="peak_artifacts_")
        self.scratch_dir = self._scratch.name

    def training_runs(self) -> list[Any]:
        """Finished runs of the experiment, newest first."""
        experiment = self.client.get_experiment_by_name(self.names.experiment)
        assert experiment is not None, f"no MLflow experiment {self.names.experiment}: train first"
        return list(
            self.client.search_runs(
                [experiment.experiment_id],
                filter_string="attributes.status = 'FINISHED'",
                order_by=["attributes.start_time DESC"],
                max_results=50,
            )
        )

    def latest_run(self) -> Any:
        runs = self.training_runs()
        assert runs, "no finished training run: run the training job (runbook)"
        return runs[0]

    def artifact(self, run_id: str, name: str) -> Path:
        folder = Path(self._scratch.name) / run_id
        folder.mkdir(exist_ok=True)
        path = folder / name
        if not path.exists():
            self.mlflow.artifacts.download_artifacts(
                run_id=run_id, artifact_path=name, dst_path=str(folder)
            )
        return path

    def parquet(self, run_id: str, name: str) -> Any:
        import pandas as pd

        return pd.read_parquet(self.artifact(run_id, name))

    def version_of_run(self, run_id: str) -> int:
        found = [
            int(v.version)
            for v in self.client.search_model_versions(f"name = '{self.names.model}'")
            if v.run_id == run_id
        ]
        assert found, f"run {run_id} registered no version of {self.names.model}"
        return max(found)

    def champion_version(self) -> int:
        return int(
            self.client.get_model_version_by_alias(
                self.names.model, peak_config.CHAMPION_ALIAS
            ).version
        )

    def threshold(self, version: int) -> float:
        tags = self.client.get_model_version(self.names.model, str(version)).tags or {}
        assert peak_config.THRESHOLD_TAG in tags, f"version {version} has no decision_threshold"
        return float(tags[peak_config.THRESHOLD_TAG])


@pytest.fixture(scope="session")
def mlflow_registry(peak_names: PeakNames) -> Mlflow:
    try:
        return Mlflow(peak_names)
    except ImportError:
        pytest.fail("mlflow is missing; install it with: pip install -e '.[integration]'")
