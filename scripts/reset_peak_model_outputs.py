"""Guarded reset of the PEAK_MODEL rebuildable tables (AC-66). Run by the user, never by an agent.

Drops exactly three tables so that the next daily run rebuilds them from Gold and Bronze weather:

  <catalog>.silver.weather_hourly
  <catalog>.ml.household_features_daily
  <catalog>.ml.household_labels_daily

It never touches Bronze (``bronze.files_weather_hourly`` and its checkpoint are the replay
source, ADR 0006), the registered model, the MLflow runs or ``gold.consumption_spike_predictions``.

Safety checks, all before the first DROP:
  1. Without ``--confirm`` the script only prints what it would do (dry run).
  2. Row counts: every table exists and has the expected row count (default: seed 42, 21,165
     weather rows and 36,480 rows in each ML table); other counts need ``--allow-other-counts``.
  3. ``bronze.files_weather_hourly`` has rows, because the weather Silver table is rebuilt from it.
  4. The AC-66 snapshot ``out/evidence/ac66_before_rebuild.json`` exists, so the evidence pair is
     not lost (``--skip-snapshot-check`` to override).

Credentials come from the Databricks CLI profile or the standard ``DATABRICKS_*`` environment
variables, as in ``tests/integration/conftest.py``. Nothing secret is read from a file or printed:
the output holds table names and row counts only.

Usage (runbook "Reset"):
  python scripts/reset_peak_model_outputs.py                 # dry run
  python scripts/reset_peak_model_outputs.py --confirm       # drop, then run the daily job
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

from smart_meter_peak_prediction import peak_config
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


class Warehouse:
    """Minimal SQL runner on the Statement Execution API (one value per statement)."""

    def __init__(self) -> None:
        from databricks.sdk import WorkspaceClient

        profile = os.environ.get("DATABRICKS_CONFIG_PROFILE")
        self.client = WorkspaceClient(profile=profile) if profile else WorkspaceClient()
        warehouse = os.environ.get("DATABRICKS_WAREHOUSE_ID", "").strip()
        if not warehouse:
            found = list(self.client.warehouses.list())
            if not found:
                raise ResetRefused("no SQL warehouse found; set DATABRICKS_WAREHOUSE_ID")
            warehouse = found[0].id
        self.warehouse_id = warehouse

    def run(self, statement: str) -> list[list[str]]:
        from databricks.sdk.service.sql import StatementState

        api = self.client.statement_execution
        response = api.execute_statement(
            statement=statement, warehouse_id=self.warehouse_id, wait_timeout="50s"
        )
        deadline = time.monotonic() + 600
        while response.status.state in (StatementState.PENDING, StatementState.RUNNING):
            if time.monotonic() > deadline:
                api.cancel_execution(response.statement_id)
                raise ResetRefused("SQL statement timed out")
            time.sleep(3)
            response = api.get_statement(response.statement_id)
        if response.status.state != StatementState.SUCCEEDED:
            message = response.status.error.message if response.status.error else "no message"
            raise ResetRefused(f"SQL failed: {message}")
        return list(response.result.data_array or []) if response.result else []

    def count(self, table: str) -> int | None:
        try:
            return int(self.run(f"SELECT count(*) FROM {table}")[0][0])  # noqa: S608
        except ResetRefused as exc:
            if "TABLE_OR_VIEW_NOT_FOUND" in str(exc) or "cannot be found" in str(exc):
                return None
            raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--confirm", action="store_true", help="drop the tables (default: dry run)")
    parser.add_argument("--allow-other-counts", action="store_true")
    parser.add_argument("--skip-snapshot-check", action="store_true")
    args = parser.parse_args(argv)

    overrides = {
        f.name: os.environ[f"SMART_METER_{f.name.upper()}"]
        for f in fields(Settings)
        if os.environ.get(f"SMART_METER_{f.name.upper()}")
    }
    settings = Settings.from_mapping(overrides)
    warehouse = Warehouse()
    zone = warehouse.run("SELECT current_timezone()")[0][0]
    if zone not in ("UTC", "Etc/UTC", "GMT"):
        print(f"refused: the warehouse session time zone is {zone}, expected UTC")
        return 2

    try:
        statements = plan(
            settings,
            warehouse.count,
            allow_other_counts=args.allow_other_counts,
            snapshot_exists=args.skip_snapshot_check or SNAPSHOT.is_file(),
        )
    except ResetRefused as exc:
        print(f"refused, nothing dropped: {exc}")
        return 2

    for statement in statements:
        print(("DROP  " if args.confirm else "would ") + statement)
    if not args.confirm:
        print("dry run: pass --confirm to drop these tables")
        return 0
    for statement in statements:
        warehouse.run(statement)
    print("done. Next: pytest -m integration tests/integration/test_peak_data.py -k ac66_after")
    print("(it rebuilds the tables and compares; runbook, Reset)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
