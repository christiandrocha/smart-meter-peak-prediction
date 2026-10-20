"""Spike 04 driver. STATUS: written, NOT RUN. Throwaway code, never imported by src/.

Creates the spike pipeline (event log published, DA-03), runs updates, asserts the outcomes,
prints PASS/FAIL per assumption and ALWAYS deletes the pipeline afterwards (only one pipeline
per type is allowed on Free Edition, so this must not linger).

Assumptions answered (record them in docs/adr/0001-runtime-environment-constraints.md):
  A-10  update 1 completes on a triggered serverless pipeline
  DA-01 failed_records of qr_03 AND qr_04 rise for the one row failing both; update 2 (no new
        input) is recorded as full recompute or changed-rows-only
  DA-02 private dataset not in UC; tables in silver and gold; view in gold
  DA-03 the event log table exists and holds flow_progress rows
  DA-07 session time zone is UTC inside the pipeline
  DA-08 import through sys.path works (the pipeline imports spike_pkg.rules)
  DA-10 timing of one update over 1.68 M synthetic Bronze rows (informational + < 2700 s)
  AC-15 expect_or_fail aborts the update; downstream MVs keep their contents

Prerequisites (run by the user): spike 00 done (catalog and schemas exist); Databricks CLI
profile or env auth; a warehouse id (`DATABRICKS_WAREHOUSE_ID` in the local .env, exported, or
--warehouse-id). Install: pip install -e ".[integration]".

Run:  python spikes/databricks/04_spike_lakeflow_pipeline/run_spike.py [--profile P] \
          [--warehouse-id W] [--catalog C] [--layout main|fallback]
For the A-09 fallback layout pass --catalog workspace --layout fallback.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.pipelines import (
    EventLogSpec,
    FileLibrary,
    PipelineLibrary,
    UpdateInfoState,
)
from databricks.sdk.service.workspace import ImportFormat

HERE = Path(__file__).resolve().parent
PACKAGE_RULES = '''\
"""Helper module synced next to the pipeline (DA-08)."""

READING_TS_SQL = (
    "coalesce(try_to_timestamp(trim(reading_ts_raw), 'yyyy-MM-dd HH:mm:ss.SSSSSSS'),"
    " try_to_timestamp(trim(reading_ts_raw), 'yyyy-MM-dd HH:mm:ss'))"
)
ENERGY_SQL = "try_cast(trim(energy_kwh_raw) AS DOUBLE)"
F02_SQL = "reading_ts IS NULL"
F03_SQL = "NOT f02 AND unix_micros(reading_ts) % 1800000000 != 0"
F04_SQL = "energy_kwh IS NULL OR isnan(energy_kwh) OR abs(energy_kwh) = double('infinity')"
F05_SQL = "NOT f04 AND energy_kwh < 0"
'''
TERMINAL = {UpdateInfoState.COMPLETED, UpdateInfoState.FAILED, UpdateInfoState.CANCELED}
N_SLOTS = 28_000  # 60 households x 28,000 half hours = 1,680,000 rows (about the seed-42 size)


class Spike:
    def __init__(self, args: argparse.Namespace) -> None:
        self.w = WorkspaceClient(profile=args.profile) if args.profile else WorkspaceClient()
        self.warehouse = args.warehouse_id or os.environ.get("DATABRICKS_WAREHOUSE_ID", "")
        if not self.warehouse:
            sys.exit("set DATABRICKS_WAREHOUSE_ID or pass --warehouse-id")
        self.catalog = args.catalog
        if args.layout == "fallback":
            self.bronze_schema, self.silver_schema, self.gold_schema = (
                "smart_meter_dev_bronze",
                "smart_meter_dev_silver",
                "smart_meter_dev_gold",
            )
        else:
            self.bronze_schema, self.silver_schema, self.gold_schema = "bronze", "silver", "gold"
        self.results: dict[str, str] = {}
        me = self.w.current_user.me().user_name
        self.root = f"/Users/{me}/spikes/lakeflow_04"
        self.pipeline_id: str | None = None

    # ------------------------------------------------------------------ helpers
    def fq(self, schema: str, name: str) -> str:
        return f"{self.catalog}.{schema}.{name}"

    def sql(self, statement: str) -> list[list[str | None]]:
        resp = self.w.statement_execution.execute_statement(
            warehouse_id=self.warehouse, statement=statement, wait_timeout="50s"
        )
        while resp.status and resp.status.state.value in ("PENDING", "RUNNING"):
            time.sleep(3)
            resp = self.w.statement_execution.get_statement(resp.statement_id)
        if resp.status.state.value != "SUCCEEDED":
            raise RuntimeError(f"SQL failed: {resp.status.error.message if resp.status.error else ''}")
        return (resp.result.data_array if resp.result and resp.result.data_array else []) or []

    def record(self, key: str, ok: bool, detail: str) -> None:
        self.results[key] = "PASS" if ok else "FAIL"
        print(f"{'PASS' if ok else 'FAIL'}  {key}: {detail}")

    def run_update(self) -> tuple[UpdateInfoState, float]:
        started = time.time()
        update_id = self.w.pipelines.start_update(self.pipeline_id, full_refresh=False).update_id
        while True:
            state = self.w.pipelines.get_update(self.pipeline_id, update_id).update.state
            if state in TERMINAL:
                self.last_update_id = update_id
                return state, time.time() - started
            time.sleep(10)

    # ------------------------------------------------------------------ setup
    def seed(self) -> None:
        bronze = self.fq(self.bronze_schema, "spike_pipeline_bronze")
        self.bronze_small, self.bronze_big = bronze, bronze + "_big"
        self.sql(f"DROP TABLE IF EXISTS {self.bronze_small}")
        self.sql(
            f"CREATE TABLE {self.bronze_small} (household_id STRING, reading_ts_raw STRING,"
            " energy_kwh_raw STRING, _source_file STRING, _ingested_at TIMESTAMP)"
        )
        ts = "'2013-01-01 00:%s:00.0000000'"
        self.sql(
            f"INSERT INTO {self.bronze_small} VALUES "
            f"('MAC000001', {ts % '00'}, ' 0.5 ', 'f1', timestamp'2026-01-01 00:00:00'),"
            f"('MAC000001', {ts % '30'}, ' 0.7 ', 'f1', timestamp'2026-01-01 00:00:00'),"
            f"('MAC000001', {ts % '30'}, ' 0.7 ', 'f2', timestamp'2026-01-02 00:00:00')," # duplicate
            f"('MAC000002', {ts % '15'}, 'Null', 'f1', timestamp'2026-01-01 00:00:00')," # QR-03 + QR-04
            f"('MAC000002', {ts % '00'}, ' 1.0 ', 'f1', timestamp'2026-01-01 00:00:00')"
        )
        self.sql(f"DROP TABLE IF EXISTS {self.bronze_big}")
        self.sql(
            f"CREATE TABLE {self.bronze_big} AS SELECT "
            "concat('MAC', lpad(cast(id % 60 AS STRING), 6, '0')) AS household_id, "
            "concat(cast(date_add(date'2012-07-01', cast(div(div(id, 60), 48) AS INT)) AS STRING), ' ', "
            "lpad(cast(div(div(id, 60) % 48, 2) AS STRING), 2, '0'), ':', "
            "lpad(cast((div(id, 60) % 2) * 30 AS STRING), 2, '0'), ':00.0000000') AS reading_ts_raw, "
            "cast(rand(42) AS STRING) AS energy_kwh_raw, "
            "concat('f', cast(div(id, 60 * 1440) AS STRING)) AS _source_file, "
            "timestamp'2026-01-01 00:00:00' AS _ingested_at "
            f"FROM range({60 * N_SLOTS})"
        )

    def upload(self) -> None:
        for sub in ("src/spike_pkg", ""):
            self.w.workspace.mkdirs(f"{self.root}/{sub}".rstrip("/"))
        files = {
            f"{self.root}/pipeline.py": (HERE / "pipeline.py").read_bytes(),
            f"{self.root}/summary_view.sql": (HERE / "summary_view.sql").read_bytes(),
            f"{self.root}/src/spike_pkg/__init__.py": b"",
            f"{self.root}/src/spike_pkg/rules.py": PACKAGE_RULES.encode(),
        }
        for path, content in files.items():
            self.w.workspace.upload(path, io.BytesIO(content), format=ImportFormat.RAW, overwrite=True)

    def spec(self, bronze_table: str) -> dict:
        return dict(
            name="spike_lakeflow_04",
            catalog=self.catalog,
            schema=self.silver_schema,
            serverless=True,
            continuous=False,
            development=True,
            channel="CURRENT",
            libraries=[
                PipelineLibrary(file=FileLibrary(path=f"{self.root}/pipeline.py")),
                PipelineLibrary(file=FileLibrary(path=f"{self.root}/summary_view.sql")),
            ],
            configuration={
                "spark.sql.session.timeZone": "UTC",
                "spike.catalog": self.catalog,
                "spike.bronze_table": bronze_table,
                "spike.src_path": f"/Workspace{self.root}/src",
            },
            event_log=EventLogSpec(
                catalog=self.catalog, schema=self.silver_schema, name="spike_event_log"
            ),
        )

    # ------------------------------------------------------------------ event log
    def expectation_failures(self, update_id: str) -> dict[str, int]:
        log = self.fq(self.silver_schema, "spike_event_log")
        rows = self.sql(
            "SELECT details:flow_progress.data_quality.expectations "
            f"FROM {log} WHERE event_type = 'flow_progress' AND origin.update_id = '{update_id}' "
            "AND details:flow_progress.data_quality.expectations IS NOT NULL"
        )
        totals: dict[str, int] = {}
        for (payload,) in rows:
            for exp in json.loads(payload):
                totals[exp["name"]] = totals.get(exp["name"], 0) + int(exp.get("failed_records", 0))
        return totals

    def evaluated_rows(self, update_id: str) -> int | None:
        log = self.fq(self.silver_schema, "spike_event_log")
        rows = self.sql(
            "SELECT details:flow_progress.metrics.num_output_rows "
            f"FROM {log} WHERE event_type = 'flow_progress' AND origin.update_id = '{update_id}' "
            "AND origin.flow_name LIKE '%spike_evaluated' "
            "AND details:flow_progress.metrics.num_output_rows IS NOT NULL"
        )
        return int(rows[-1][0]) if rows else None

    def count(self, table: str) -> int:
        return int(self.sql(f"SELECT count(*) FROM {table}")[0][0])

    # ------------------------------------------------------------------ the spike
    def run(self) -> None:
        for p in self.w.pipelines.list_pipelines(filter="name LIKE 'spike_lakeflow_04'"):
            self.w.pipelines.delete(p.pipeline_id)  # leftover from a crashed run
        self.seed()
        self.upload()
        created = self.w.pipelines.create(allow_duplicate_names=True, **self.spec(self.bronze_small))
        self.pipeline_id = created.pipeline_id
        print("pipeline created:", self.pipeline_id)

        state, secs = self.run_update()
        self.record("A-10", state == UpdateInfoState.COMPLETED, f"update 1 {state.value} in {secs:.0f} s")
        first_update = self.last_update_id

        # DA-03, DA-01
        log_rows = self.sql(
            f"SELECT count(*) FROM {self.fq(self.silver_schema, 'spike_event_log')} "
            f"WHERE event_type = 'flow_progress' AND origin.update_id = '{first_update}'"
        )
        self.record("DA-03", int(log_rows[0][0]) > 0, f"{log_rows[0][0]} flow_progress rows in the published log")
        fails1 = self.expectation_failures(first_update)
        both = fails1.get("qr_03_on_30_min_grid") == 1 and fails1.get("qr_04_energy_numeric") == 1
        self.record("DA-01 two counters", both, f"failed_records per expectation, update 1: {fails1}")
        self.record("DA-01 duplicate counter", fails1.get("qr_09_first_ingested_wins") == 1, str(fails1))

        silver = self.fq(self.silver_schema, "spike_readings")
        quarantine = self.fq(self.silver_schema, "spike_quarantine")
        daily = self.fq(self.gold_schema, "spike_daily")
        counts1 = (self.count(silver), self.count(quarantine), self.count(daily))
        print("tables after update 1 (silver, quarantine, daily), expected (3, 1, 2):", counts1)

        # DA-01 second update, no new input
        state2, _ = self.run_update()
        fails2 = self.expectation_failures(self.last_update_id)
        evaluated2 = self.evaluated_rows(self.last_update_id)
        mode = "full recompute" if evaluated2 == 5 else f"changed rows only or other ({evaluated2})"
        self.record("DA-01 update 2", state2 == UpdateInfoState.COMPLETED and fails2 == fails1, f"counts {fails2}; evaluated rows {evaluated2}: {mode}")
        self.results["DA-01 evaluated-row mode"] = mode

        # DA-02, DA-07, DA-08
        info = self.sql(
            f"SELECT table_schema, table_name, table_type FROM {self.catalog}.information_schema.tables "
            "WHERE table_name LIKE 'spike_%'"
        )
        names = {(r[0], r[1], r[2]) for r in info}
        private_hidden = not any(n[1] == "spike_evaluated" for n in names)
        view_ok = (self.gold_schema, "spike_summary", "VIEW") in names
        two_schemas = {self.silver_schema, self.gold_schema} <= {n[0] for n in names}
        self.record("DA-02 private dataset hidden", private_hidden, str(sorted(names)))
        self.record("DA-02 two schemas", two_schemas, "tables published in silver and gold")
        self.record("DA-02 persisted view", view_ok, "CREATE VIEW from the pipeline SQL file")
        tz = self.sql(f"SELECT tz FROM {self.fq(self.silver_schema, 'spike_tz_check')}")
        self.record("DA-07", bool(tz) and tz[0][0] == "UTC", f"current_timezone() in the pipeline: {tz}")
        self.record("DA-08", state == UpdateInfoState.COMPLETED, "update 1 imported spike_pkg.rules through sys.path")

        # AC-15: expect_or_fail aborts the update, downstream MVs keep their contents
        self.sql(
            f"INSERT INTO {self.bronze_small} VALUES ('BAD', '2013-01-01 01:00:00.0000000', '1', 'f3', current_timestamp())"
        )
        state3, _ = self.run_update()
        after = (self.count(silver), self.count(quarantine), self.count(daily))
        self.record(
            "AC-15 expect_or_fail",
            state3 == UpdateInfoState.FAILED and after == counts1,
            f"update 3 {state3.value}; contents before {counts1}, after {after}",
        )
        self.sql(f"DELETE FROM {self.bronze_small} WHERE household_id = 'BAD'")

        # DA-10 / AC-30: one update over ~1.68 M rows
        self.w.pipelines.update(self.pipeline_id, **self.spec(self.bronze_big))
        state4, secs4 = self.run_update()
        self.record(
            "DA-10 timing",
            state4 == UpdateInfoState.COMPLETED and secs4 < 2700,
            f"one update over {60 * N_SLOTS:,} rows: {state4.value} in {secs4:.0f} s (target < 900 s)",
        )

    def cleanup(self) -> None:
        if self.pipeline_id:
            try:
                self.w.pipelines.delete(self.pipeline_id)
                print("pipeline deleted:", self.pipeline_id)
            except Exception as exc:  # noqa: BLE001
                print(f"WARNING: delete the pipeline manually ({type(exc).__name__}); it blocks PR 2")
        try:
            self.w.workspace.delete(f"{self.root}", recursive=True)
        except Exception:  # noqa: BLE001
            pass
        for stmt in (
            f"DROP TABLE IF EXISTS {self.fq(self.silver_schema, 'spike_event_log')}",
            f"DROP VIEW IF EXISTS {self.fq(self.gold_schema, 'spike_summary')}",
            f"DROP TABLE IF EXISTS {self.bronze_small}",
            f"DROP TABLE IF EXISTS {self.bronze_big}",
        ):
            try:
                self.sql(stmt)
            except Exception:  # noqa: BLE001
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--catalog", default="smart_meter_dev")
    parser.add_argument("--layout", choices=["main", "fallback"], default="main")
    parser.add_argument("--profile")
    parser.add_argument("--warehouse-id")
    args = parser.parse_args()
    spike = Spike(args)
    spike.bronze_small = spike.bronze_big = ""
    try:
        spike.run()
    finally:
        spike.cleanup()
    print("\nSUMMARY (record in ADR 0001):")
    for key, value in spike.results.items():
        print(f"  {key}: {value}")
    return 1 if "FAIL" in spike.results.values() else 0


if __name__ == "__main__":
    sys.exit(main())
