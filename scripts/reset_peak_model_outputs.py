"""Guarded reset of the PEAK_MODEL rebuildable tables (AC-66). Run by the user, never by an agent.

Drops exactly three tables so that the AC-66 rebuild leg (or a later daily run) rebuilds them from
Gold and Bronze weather:

  <catalog>.silver.weather_hourly
  <catalog>.ml.household_features_daily
  <catalog>.ml.household_labels_daily

It never touches Bronze (``bronze.files_weather_hourly`` and its checkpoint are the replay
source, ADR 0006), the registered model, the MLflow runs or ``gold.consumption_spike_predictions``.

Safety checks, all before the first DROP:
  1. Without ``--confirm`` the script only prints what it would do (dry run). The dry run runs
     every check below as well, so it predicts the outcome of ``--confirm``.
  2. The warehouse session time zone is UTC.
  3. Row counts: every table exists and has the expected row count (default: seed 42, 21,165
     weather rows and 36,480 rows in each ML table); other counts need ``--allow-other-counts``.
  4. ``bronze.files_weather_hourly`` has rows, because the weather Silver table is rebuilt from it.
  5. The AC-66 snapshot ``out/evidence/ac66_before_rebuild.json`` exists, so the evidence pair is
     not lost (``--skip-snapshot-check`` to override).
  6. Idle check, the last read before the first DROP: the jobs ``smart_meter_peak_model`` and
     ``smart_meter_peak_model_training`` (found by name, development prefix stripped) have no
     active run. A run in any state other than TERMINATED, SKIPPED or INTERNAL_ERROR, or a job
     that is not found exactly once or cannot be read, refuses (ADR 0014). The dry run runs the
     idle check too. No flag skips the idle check. A run started in the window between the idle
     check and the first DROP is not seen: start no job run until the reset has ended.

Every refusal is one line that starts with ``refused, nothing dropped: `` and exits 2; nothing was
dropped. Wait until the named run ends (or fix the named cause), then run the reset again. A failed
DROP stops the drops and exits 1 with one line that names the tables already dropped (runbook
"Reset"). Exit 0: dry run, or the three tables dropped.

Credentials come from the Databricks CLI profile or the standard ``DATABRICKS_*`` environment
variables, as in ``tests/integration/conftest.py``. Nothing secret is read from a file or printed:
the output holds table names and row counts only.

Usage (runbook "Reset"):
  python scripts/reset_peak_model_outputs.py                 # dry run
  python scripts/reset_peak_model_outputs.py --confirm       # drop; then -k ac66_rebuild_leg
Optional: DATABRICKS_CONFIG_PROFILE, DATABRICKS_WAREHOUSE_ID, SMART_METER_<FIELD> (as the tests).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from smart_meter_peak_prediction import peak_config, pipeline_guard
from smart_meter_peak_prediction.config import Settings

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "out" / "evidence" / "ac66_before_rebuild.json"
EXPECTED_ROWS = {
    peak_config.SILVER_WEATHER: 21165,
    peak_config.FEATURES: 36480,
    peak_config.LABELS: 36480,
}


class ResetRefused(Exception):
    """A safety check failed; nothing was dropped."""


@dataclass(frozen=True)
class Target:
    table: str  # fully qualified
    expected_rows: int


def targets(settings: Settings) -> list[Target]:
    return [
        Target(
            peak_config.silver_weather_table(settings), EXPECTED_ROWS[peak_config.SILVER_WEATHER]
        ),
        Target(peak_config.features_table(settings), EXPECTED_ROWS[peak_config.FEATURES]),
        Target(peak_config.labels_table(settings), EXPECTED_ROWS[peak_config.LABELS]),
    ]


def plan(
    settings: Settings,
    count: Callable[[str], int | None],
    *,
    allow_other_counts: bool = False,
    snapshot_exists: bool = True,
) -> list[str]:
    """Return the DROP statements, or raise ``ResetRefused``. ``count`` returns None if missing."""
    problems: list[str] = []
    chosen = targets(settings)
    for target in chosen:
        rows = count(target.table)
        if rows is None:
            problems.append(f"{target.table} does not exist")
        elif rows != target.expected_rows and not allow_other_counts:
            problems.append(f"{target.table} has {rows} rows, expected {target.expected_rows}")
    bronze = peak_config.bronze_weather_table(settings)
    bronze_rows = count(bronze)
    if not bronze_rows:
        problems.append(
            f"{bronze} is empty or missing: the weather Silver table could not be rebuilt"
        )
    if not snapshot_exists:
        problems.append(
            f"snapshot {SNAPSHOT.relative_to(ROOT)} is missing: run "
            "test_ac66_before_rebuild_snapshot first"
        )
    if problems:
        raise ResetRefused("; ".join(problems))
    return [f"DROP TABLE {target.table}" for target in chosen]


IDLE_SET = (pipeline_guard.PEAK_JOB, pipeline_guard.TRAINING_JOB)  # D-104, DA-72
REFUSED = "refused, nothing dropped: "
UTC_ZONES = ("UTC", "Etc/UTC", "GMT")
STATEMENT_WAIT = "20s"  # below the 30 s HTTP limit of CLIENT_LIMITS (DA-63)
STATEMENT_DEADLINE_S = 600
ACTIVE_STATEMENT_STATES = ("PENDING", "RUNNING")  # Statement Execution states, not run states
ACTION_WAIT = "wait until the named run ends, then run the reset again"
ACTION_FIX = (
    "fix the named cause (deployment, permission or API availability), then run the reset again"
)
ACTION_BOTH = "wait until the named run ends and fix the named cause, then run the reset again"


class StatementFailed(ResetRefused):
    """A statement ended other than SUCCEEDED; ``detail`` keeps the raw text (DA-66)."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        lines = detail.strip().splitlines()
        first = pipeline_guard.redact(lines[0].strip() if lines else "")
        super().__init__(f"SQL failed: {first[: pipeline_guard.MAX_ERROR_CHARS] or 'no message'}")


def build_client() -> Any:
    """The one workspace client: CLI profile or DATABRICKS_* variables, shipped limits (DA-63)."""
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.config import Config

    options: dict[str, Any] = dict(pipeline_guard.CLIENT_LIMITS)
    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE")
    if profile:
        options["profile"] = profile
    return WorkspaceClient(config=Config(**options))


class Warehouse:
    """Minimal SQL runner on the Statement Execution API (one value per statement)."""

    def __init__(self, client: Any) -> None:
        self.client = client
        warehouse = os.environ.get("DATABRICKS_WAREHOUSE_ID", "").strip()
        if not warehouse:
            found = list(client.warehouses.list())
            if not found:
                raise ResetRefused("no SQL warehouse found; set DATABRICKS_WAREHOUSE_ID")
            warehouse = found[0].id
        self.warehouse_id = warehouse

    def run(self, statement: str) -> list[list[str]]:
        api = self.client.statement_execution
        response = api.execute_statement(
            statement=statement, warehouse_id=self.warehouse_id, wait_timeout=STATEMENT_WAIT
        )
        deadline = time.monotonic() + STATEMENT_DEADLINE_S
        while _state(response) in ACTIVE_STATEMENT_STATES:
            if time.monotonic() > deadline:
                api.cancel_execution(response.statement_id)
                raise ResetRefused("SQL statement timed out")
            time.sleep(3)
            response = api.get_statement(response.statement_id)
        if _state(response) != "SUCCEEDED":
            error = getattr(response.status, "error", None)
            raise StatementFailed(getattr(error, "message", None) or "no message")
        return list(response.result.data_array or []) if response.result else []

    def count(self, table: str) -> int | None:
        try:
            return int(self.run(f"SELECT count(*) FROM {table}")[0][0])  # noqa: S608
        except StatementFailed as exc:
            if "TABLE_OR_VIEW_NOT_FOUND" in exc.detail or "cannot be found" in exc.detail:
                return None
            raise


def _state(response: Any) -> str:
    state = getattr(getattr(response, "status", None), "state", None)
    return str(getattr(state, "value", state))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--confirm", action="store_true", help="drop the tables (default: dry run)")
    parser.add_argument("--allow-other-counts", action="store_true")
    parser.add_argument("--skip-snapshot-check", action="store_true")
    return parser


def _settings() -> Settings:
    overrides = {
        f.name: os.environ[f"SMART_METER_{f.name.upper()}"]
        for f in fields(Settings)
        if os.environ.get(f"SMART_METER_{f.name.upper()}")
    }
    return Settings.from_mapping(overrides)


def _say(line: str) -> None:
    print(pipeline_guard.redact(" ".join(line.splitlines())))  # G-63


def _refuse(text: str) -> int:
    _say(REFUSED + text)
    return 2


def _reason(exc: Exception) -> str:
    return str(exc) if isinstance(exc, ResetRefused) else pipeline_guard.describe_error(exc)


def _idle_check(client: Any) -> tuple[list[str], str | None]:
    """Idle lines, or the idle-check problem (G-59 to G-61); never raises."""
    try:
        report = pipeline_guard.check_jobs(client, IDLE_SET)
    except Exception as exc:  # noqa: BLE001 - fail closed
        error = pipeline_guard.describe_error(exc)
        return [], f"idle check: internal error: {error}; action: {ACTION_FIX}"
    if report.ok:
        return report.idle_lines(), None
    if report.blocked and report.has_unreadable:
        action = ACTION_BOTH
    else:
        action = ACTION_WAIT if report.blocked else ACTION_FIX
    return [], f"idle check: {'; '.join(report.problems())}; action: {action}"


def _drop_failure(statements: list[str], done: int, exc: Exception) -> str:
    tables = [statement.removeprefix("DROP TABLE ") for statement in statements]
    return (
        f"drop phase failed: dropped: {', '.join(tables[:done]) or 'none'}; "
        f"failed: {tables[done]}: {_reason(exc)}; "
        f"not attempted: {', '.join(tables[done + 1 :]) or 'none'}; check the three tables "
        'before any other step (runbook section 9, "If the drop phase fails")'
    )


def main(
    argv: list[str] | None = None,
    *,
    client_factory: Callable[[], Any] = build_client,
    snapshot_exists: Callable[[], bool] | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = _settings()
    except Exception as exc:  # noqa: BLE001
        return _refuse(f"settings: {pipeline_guard.describe_error(exc)}")
    try:
        client = client_factory()
    except Exception as exc:  # noqa: BLE001
        jobs = ", ".join(f"job {name}" for name in IDLE_SET)
        error = pipeline_guard.describe_error(exc)
        return _refuse(f"workspace client: {error}; not read: the SQL warehouse, {jobs}")
    try:
        warehouse = Warehouse(client)
    except Exception as exc:  # noqa: BLE001
        return _refuse(f"warehouse lookup: {_reason(exc)}")
    try:
        zone = str(warehouse.run("SELECT current_timezone()")[0][0])
    except Exception as exc:  # noqa: BLE001
        return _refuse(f"time-zone query: {_reason(exc)}")
    if zone not in UTC_ZONES:
        return _refuse(f"the warehouse session time zone is {zone}, expected UTC")

    problems: list[str] = []
    statements: list[str] = []
    exists = snapshot_exists or SNAPSHOT.is_file
    try:
        statements = plan(
            settings,
            warehouse.count,
            allow_other_counts=args.allow_other_counts,
            snapshot_exists=args.skip_snapshot_check or exists(),
        )
    except StatementFailed as exc:
        problems.append(f"row counts: {exc}")
    except ResetRefused as exc:
        problems.append(str(exc))
    except Exception as exc:  # noqa: BLE001
        problems.append(f"row counts: {pipeline_guard.describe_error(exc)}")
    idle_lines, idle_problem = _idle_check(client)  # the last read before the first DROP
    if idle_problem:
        problems.append(idle_problem)
    if problems:
        return _refuse("; ".join(problems))

    for line in idle_lines:
        _say(line)
    for statement in statements:
        _say(("DROP  " if args.confirm else "would ") + statement)
    if not args.confirm:
        _say("dry run: pass --confirm to drop these tables")
        return 0
    for done, statement in enumerate(statements):
        try:
            warehouse.run(statement)
        except Exception as exc:  # noqa: BLE001
            _say(_drop_failure(statements, done, exc))
            return 1
    _say(
        "done. Next (rebuild leg): pytest -m integration "
        "tests/integration/test_peak_data.py -k ac66_rebuild_leg"
    )
    _say(
        "(it starts ingest_weather, build_weather_silver, build_features and build_labels itself "
        "and compares; then the AC-66 verdict; runbook, Reset)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
