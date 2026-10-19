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
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import fields
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from smart_meter_peak_prediction import metrics
from smart_meter_peak_prediction.config import Settings
from smart_meter_peak_prediction.rules import DROP_RULE_PRECEDENCE

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "out" / "evidence"
CONFIG_MANIFEST = ROOT / "config" / "sample_manifest.json"
DEFAULT_SAMPLE_MANIFEST = ROOT / "data" / "sample" / "seed42" / "manifest.json"
CONTRACTS_DIR = ROOT / "docs" / "contracts"

JOB_NAME = "smart_meter_ingestion"
PIPELINE_NAME = "smart_meter_silver_gold"
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
            job_id=job.job_id, completed_only=True, expand_tasks=True, limit=50
        )
        full = [
            r
            for r in runs
            if r.state
            and r.state.result_state
            and r.state.result_state.value == "SUCCESS"
            and {t.task_key for t in r.tasks or []} == all_tasks
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
