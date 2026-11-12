"""``main()`` of the user-run reset on fakes (RESET_GUARD AC-189 to AC-196, AC-198 to AC-200).

No workspace and no ``databricks-sdk``: the workspace client and the snapshot check are injected
into ``main``. Every test that guards an acceptance criterion names it. "Every table check passes"
means time zone ``UTC``, the expected counts, Bronze weather rows and an existing snapshot.
"""

from __future__ import annotations

import inspect
import subprocess
import sys
from enum import Enum
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
import reset_peak_model_outputs as reset
from support import reset_fakes as fakes

from smart_meter_peak_prediction import pipeline_guard
from smart_meter_peak_prediction.config import Settings

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "refused, nothing dropped: "
BUSY = "wait until the named run ends, then run the reset again"
TZ = "SELECT current_timezone()"
FEATURES_COUNT = f"SELECT count(*) FROM {fakes.FEATURES}"  # noqa: S608
BRONZE_COUNT = f"SELECT count(*) FROM {fakes.BRONZE}"  # noqa: S608
NAME_OF = {fakes.PEAK_ID: fakes.PEAK, fakes.TRAINING_ID: fakes.TRAINING}


class RunState(Enum):
    RUNNING = "RUNNING"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """No ambient settings or profile; ``time.sleep`` is counted and does not wait."""
    import os

    for name in list(os.environ):
        if name.startswith(("SMART_METER_", "DATABRICKS_")):
            monkeypatch.delenv(name)
    sleeps: list[float] = []
    monkeypatch.setattr(reset.time, "sleep", sleeps.append)
    return sleeps


def invoke(
    capsys: pytest.CaptureFixture[str],
    client: Any,
    argv: list[str],
    *,
    snapshot: bool = True,
    factory: Any = None,
) -> tuple[int, list[str], str]:
    code = reset.main(
        argv,
        client_factory=factory or fakes.factory(client),
        snapshot_exists=lambda: snapshot,
    )
    captured = capsys.readouterr()
    return code, captured.out.splitlines(), captured.out + captured.err


def one_refusal(code: int, lines: list[str], everything: str) -> str:
    assert code == 2
    assert len(lines) == 1, lines
    assert lines[0].startswith(PREFIX)
    assert "Traceback" not in everything
    return lines[0]


def busy_client(job_id: int, state: Any, **run_options: Any) -> fakes.FakeClient:
    return fakes.FakeClient(runs={job_id: [fakes.run(state, **run_options)]})


# ----------------------------------------------------------------------------- AC-189
STATES = [
    ("QUEUED", "QUEUED"),
    ("PENDING", "PENDING"),
    ("RUNNING", "RUNNING"),
    ("TERMINATING", "TERMINATING"),
    ("BLOCKED", "BLOCKED"),
    ("WAITING_FOR_RETRY", "WAITING_FOR_RETRY"),
    ("NEW_STATE", "NEW_STATE"),
    (RunState.RUNNING, "RUNNING"),
    (None, "UNKNOWN"),
]


@pytest.mark.parametrize("job_id", [fakes.PEAK_ID, fakes.TRAINING_ID])
@pytest.mark.parametrize(("state", "shown"), STATES)
def test_ac189_an_active_run_of_either_peak_job_refuses_both_modes(
    capsys: pytest.CaptureFixture[str], job_id: int, state: Any, shown: str
) -> None:
    for argv in (["--confirm"], []):
        client = busy_client(job_id, state)
        code, lines, everything = invoke(capsys, client, argv)
        line = one_refusal(code, lines, everything)
        expected = (
            f"job {NAME_OF[job_id]} (job id {job_id}): active run 7, state {shown}, "
            f"started {fakes.START_TEXT}"
        )
        assert expected in line
        assert f"action: {BUSY}" in line
        assert client.drops() == []
        assert fakes.no_secret(everything)
        assert fakes.utc_only(everything)


@pytest.mark.parametrize("start", [None, 0, "", "2025-11-12T10:00:00"])
def test_ac189_a_run_without_start_time_is_shown_not_started(
    capsys: pytest.CaptureFixture[str], start: Any
) -> None:
    client = busy_client(fakes.TRAINING_ID, "QUEUED", start_time=start)
    code, lines, everything = invoke(capsys, client, ["--confirm"])
    line = one_refusal(code, lines, everything)
    assert "active run 7, state QUEUED, started not started" in line
    assert fakes.utc_only(everything)


# ----------------------------------------------------------------------------- AC-190
def _other_job(**kwargs: Any) -> Any:
    name = fakes.DEV + "other_job"
    return SimpleNamespace(job_id=kwargs["job_id"], settings=SimpleNamespace(name=name))


AC190_CASES: dict[str, tuple[dict[str, Any], list[str]]] = {
    "client factory": ({}, ["workspace client", "no workspace"]),
    "get raises": (
        {"overrides": {"jobs.get": RuntimeError("get down")}},
        [f"job {fakes.PEAK} (job id 101): job: RuntimeError: get down"],
    ),
    "permission denied": (
        {"overrides": {"jobs.get": fakes.PermissionDenied()}},
        [f"job {fakes.PEAK} (job id 101): job: PermissionDenied (PERMISSION_DENIED)"],
    ),
    "no deployed job": (
        {"jobs": [(101, fakes.DEV + fakes.PEAK), (103, fakes.DEV + fakes.INGESTION)]},
        [f"job {fakes.TRAINING} (job id not resolved): job list: no deployed job named"],
    ),
    "two deployed jobs": (
        {"jobs": [*fakes.DEFAULT_JOBS, (104, "[dev other] " + fakes.TRAINING)]},
        [f"'{fakes.TRAINING}' is not unique (job ids: 102, 104)"],
    ),
    "id names another job": (
        {"overrides": {"jobs.get": _other_job}},
        ["the id names another job"],
    ),
    "list runs raises": (
        {"runs": {101: RuntimeError("runs down"), 102: RuntimeError("runs down")}},
        [f"job {fakes.PEAK} (job id 101): active runs: RuntimeError: runs down"],
    ),
    "job list raises": (
        {"overrides": {"jobs.list": RuntimeError("list down")}},
        [f"job {fakes.PEAK} (job id not resolved): job list: RuntimeError: list down"],
    ),
    "page full": (
        {"jobs": [(1000 + i, f"{fakes.DEV}other_{i}") for i in range(100)]},
        ["100 jobs listed, the page is full"],
    ),
}


def ac190_client(case: str) -> tuple[fakes.FakeClient, Any]:
    options = AC190_CASES[case][0]
    client = fakes.FakeClient(**options)
    if case == "client factory":
        return client, fakes.raising_factory(RuntimeError("no workspace"))
    return client, None


@pytest.mark.parametrize("case", AC190_CASES)
def test_ac190_an_unreadable_peak_job_fails_closed(
    capsys: pytest.CaptureFixture[str], case: str
) -> None:
    client, factory = ac190_client(case)
    code, lines, everything = invoke(capsys, client, ["--confirm"], factory=factory)
    line = one_refusal(code, lines, everything)
    for fragment in AC190_CASES[case][1]:
        assert fragment in line, (fragment, line)
    assert client.drops() == []
    assert client.forbidden == []


# ----------------------------------------------------------------------------- AC-191
@pytest.mark.parametrize("enum_states", [False, True])
def test_ac191_confirm_with_both_jobs_idle_drops_the_three_tables_in_order(
    capsys: pytest.CaptureFixture[str], enum_states: bool
) -> None:
    race = [fakes.run("TERMINATED"), fakes.run("SKIPPED", 8), fakes.run("INTERNAL_ERROR", 9)]
    client = fakes.FakeClient(runs={101: race, 102: race}, enum_states=enum_states)
    code, lines, everything = invoke(capsys, client, ["--confirm"])
    assert code == 0
    assert lines[:2] == [
        f"idle check: job {fakes.PEAK} (job id 101): 0 active runs",
        f"idle check: job {fakes.TRAINING} (job id 102): 0 active runs",
    ]
    assert lines[2:5] == [f"DROP  {statement}" for statement in fakes.DROPS]
    assert lines[5].startswith("done. Next (rebuild leg)")
    assert len(lines) == 7
    assert client.drops() == fakes.DROPS
    first_drop = client.log.index(f"sql:{fakes.DROPS[0]}")
    last_read = max(i for i, entry in enumerate(client.log) if entry.startswith("jobs."))
    assert last_read < first_drop
    assert "Traceback" not in everything


# ----------------------------------------------------------------------------- AC-192
AC192_CASES: dict[str, tuple[dict[str, Any], str | None]] = {
    "client factory": ({}, None),
    "empty warehouse list": ({"warehouses": []}, "warehouse lookup: no SQL warehouse found"),
    "warehouse list raises": (
        {"overrides": {"warehouses.list": RuntimeError("down")}},
        "warehouse lookup: RuntimeError: down",
    ),
    "time zone query failed": (
        {"sql": {TZ: "FAILED:[SERVER] unavailable"}},
        "time-zone query: SQL failed: [SERVER] unavailable",
    ),
    "time zone query raises": (
        {"overrides": {"statement_execution.execute_statement": RuntimeError("socket")}},
        "time-zone query: RuntimeError: socket",
    ),
    "time zone not UTC": (
        {"sql": {TZ: "Europe/Berlin"}},
        "the warehouse session time zone is Europe/Berlin, expected UTC",
    ),
}


@pytest.mark.parametrize("argv", [[], ["--confirm"]])
@pytest.mark.parametrize("case", AC192_CASES)
def test_ac192_connection_failures_print_one_refusal_line(
    capsys: pytest.CaptureFixture[str], case: str, argv: list[str]
) -> None:
    options, expected = AC192_CASES[case]
    client = fakes.FakeClient(**options)
    factory = (
        fakes.raising_factory(RuntimeError("no workspace")) if case == "client factory" else None
    )
    code, lines, everything = invoke(capsys, client, argv, factory=factory)
    line = one_refusal(code, lines, everything)
    if expected is not None:
        assert line.startswith(PREFIX + expected), line
    if case == "client factory":
        assert line == (
            PREFIX + "workspace client: RuntimeError: no workspace; not read: the SQL warehouse, "
            f"job {fakes.PEAK}, job {fakes.TRAINING}"
        )
    assert client.drops() == []
    assert not [s for s in client.statements() if s.startswith("SELECT count(*)")]
    assert client.jobs_entries() == []


def test_ac192_missing_sdk_refuses_through_the_default_factory(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("databricks", "databricks.sdk", "databricks.sdk.config"):
        monkeypatch.setitem(sys.modules, name, None)
    code = reset.main([], snapshot_exists=lambda: True)
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert code == 2
    assert len(lines) == 1
    assert lines[0].startswith(PREFIX + "workspace client: ModuleNotFoundError")
    assert "Traceback" not in captured.out + captured.err


# ----------------------------------------------------------------------------- AC-193
def test_ac193_every_check_completes_before_the_first_drop(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = fakes.FakeClient()
    code, _, _ = invoke(capsys, client, ["--confirm"])
    assert code == 0
    log = client.log
    first_drop = log.index(f"sql:{fakes.DROPS[0]}")
    assert all(i < first_drop for i, entry in enumerate(log) if entry.startswith("jobs."))
    assert log.index(f"sql:{TZ}") < first_drop
    counts = [i for i, entry in enumerate(log) if entry.startswith("sql:SELECT count(*)")]
    assert len(counts) == 4
    assert all(i < first_drop for i in counts)
    last_jobs = max(i for i, entry in enumerate(log) if entry.startswith("jobs."))
    between = [e for e in log[last_jobs + 1 : first_drop] if e.startswith("sql:")]
    assert between == []


FAILING_CHECKS = {
    "time zone": ({"sql": {TZ: "Europe/Berlin"}}, True, "the warehouse session time zone is"),
    "idle set": ({"runs": {101: [fakes.run("RUNNING")]}}, True, "idle check: job"),
    "row count": (
        {"sql": {FEATURES_COUNT: 5}},
        True,
        f"{fakes.FEATURES} has 5 rows, expected 36480",
    ),
    "bronze empty": (
        {"sql": {BRONZE_COUNT: 0}},
        True,
        f"{fakes.BRONZE} is empty or missing: the weather Silver table could not be rebuilt",
    ),
    "snapshot missing": (
        {},
        False,
        "snapshot out/evidence/ac66_before_rebuild.json is missing: run "
        "test_ac66_before_rebuild_snapshot first",
    ),
}


@pytest.mark.parametrize("check", FAILING_CHECKS)
def test_ac193_each_failing_check_refuses_without_a_drop(
    capsys: pytest.CaptureFixture[str], check: str
) -> None:
    options, snapshot, text = FAILING_CHECKS[check]
    client = fakes.FakeClient(**options)
    code, lines, everything = invoke(capsys, client, ["--confirm"], snapshot=snapshot)
    line = one_refusal(code, lines, everything)
    assert client.drops() == []
    if check in ("row count", "bronze empty", "snapshot missing"):
        assert line == PREFIX + text
        assert client.jobs_entries()  # the idle check ran as well (G-62)
    else:
        assert text in line


def test_ac193_count_and_idle_problems_share_one_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = fakes.FakeClient(
        sql={FEATURES_COUNT: 5}, runs={fakes.TRAINING_ID: [fakes.run("RUNNING")]}
    )
    code, lines, everything = invoke(capsys, client, ["--confirm"])
    line = one_refusal(code, lines, everything)
    assert line == (
        f"{PREFIX}{fakes.FEATURES} has 5 rows, expected 36480; idle check: job {fakes.TRAINING} "
        f"(job id 102): active run 7, state RUNNING, started {fakes.START_TEXT}; action: {BUSY}"
    )


# ----------------------------------------------------------------------------- AC-194
def test_ac194_dry_run_checks_the_jobs_and_sends_only_select(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = fakes.FakeClient()
    code, lines, _ = invoke(capsys, client, [])
    assert code == 0
    assert client.jobs_entries() == IDLE_READS
    assert lines == [
        f"idle check: job {fakes.PEAK} (job id 101): 0 active runs",
        f"idle check: job {fakes.TRAINING} (job id 102): 0 active runs",
        *[f"would {statement}" for statement in fakes.DROPS],
        "dry run: pass --confirm to drop these tables",
    ]
    assert client.statements()
    assert all(statement.startswith("SELECT") for statement in client.statements())


IDLE_READS = [
    "jobs.list(limit=100)",
    "jobs.get(101)",
    f"jobs.list(name={fakes.DEV}{fakes.PEAK})",
    "jobs.list_runs(101)",
    "jobs.list(limit=100)",
    "jobs.get(102)",
    f"jobs.list(name={fakes.DEV}{fakes.TRAINING})",
    "jobs.list_runs(102)",
]


# ----------------------------------------------------------------------------- AC-195
def test_ac195_no_option_or_variable_skips_the_idle_check(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABRICKS_CONFIG_PROFILE", "dev")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", fakes.WAREHOUSE_ID)
    defaults = Settings()
    for name in vars(defaults):
        monkeypatch.setenv(f"SMART_METER_{name.upper()}", str(getattr(defaults, name)))
    client = busy_client(fakes.TRAINING_ID, "RUNNING")
    argv = ["--confirm", "--allow-other-counts", "--skip-snapshot-check"]
    code, lines, everything = invoke(capsys, client, argv, snapshot=False)
    line = one_refusal(code, lines, everything)
    assert f"job {fakes.TRAINING} (job id 102): active run 7" in line
    assert client.drops() == []
    options = sorted(s for a in reset.build_parser()._actions for s in a.option_strings)
    assert options == ["--allow-other-counts", "--confirm", "--help", "--skip-snapshot-check", "-h"]
    assert list(inspect.signature(reset.main).parameters) == [
        "argv",
        "client_factory",
        "snapshot_exists",
    ]


# ----------------------------------------------------------------------------- AC-196
def test_ac196_a_failed_drop_stops_and_exits_1(capsys: pytest.CaptureFixture[str]) -> None:
    client = fakes.FakeClient(sql={fakes.DROPS[1]: "FAILED:[TABLE_LOCKED] busy"})
    code, lines, everything = invoke(capsys, client, ["--confirm"])
    assert code == 1
    assert client.drops() == fakes.DROPS[:2]
    assert lines[-1].startswith(
        f"drop phase failed: dropped: {fakes.WEATHER}; failed: {fakes.FEATURES}: "
        f"SQL failed: [TABLE_LOCKED] busy; not attempted: {fakes.LABELS}; "
    )
    assert "Traceback" not in everything
    assert "nothing dropped" not in everything
    assert not any(line.startswith("done.") for line in lines)

    first = fakes.FakeClient(sql={fakes.DROPS[0]: "FAILED:[TABLE_LOCKED] busy"})
    code, lines, everything = invoke(capsys, first, ["--confirm"])
    assert code == 1
    assert first.drops() == fakes.DROPS[:1]
    assert "dropped: none; failed: " in lines[-1]
    assert "nothing dropped" not in everything


# ----------------------------------------------------------------------------- AC-198
def _scenarios() -> dict[str, tuple[fakes.FakeClient, list[str], Any]]:
    race = {fakes.PEAK_ID: [fakes.run("TERMINATED")]}
    return {
        "busy peak": (busy_client(101, "RUNNING"), ["--confirm"], None),
        "busy training": (busy_client(102, "QUEUED"), [], None),
        "unreadable": (
            fakes.FakeClient(overrides={"jobs.get": fakes.PermissionDenied()}),
            ["--confirm"],
            None,
        ),
        "factory": (fakes.FakeClient(), ["--confirm"], fakes.raising_factory(RuntimeError("x"))),
        "idle confirm": (fakes.FakeClient(runs=race), ["--confirm"], None),
        "idle dry": (fakes.FakeClient(), [], None),
        "time zone": (fakes.FakeClient(sql={TZ: "Europe/Berlin"}), ["--confirm"], None),
        "row count": (fakes.FakeClient(sql={FEATURES_COUNT: 5}), ["--confirm"], None),
        "drop failed": (
            fakes.FakeClient(sql={fakes.DROPS[2]: "FAILED:[X] no"}),
            ["--confirm"],
            None,
        ),
        "secret": (
            fakes.FakeClient(overrides={"jobs.get": fakes.secret_error()}),
            ["--confirm"],
            None,
        ),
    }


READ_ONLY = {
    *pipeline_guard.JOB_READ_CALLS,
    "warehouses.list",
    "statement_execution.execute_statement",
    "statement_execution.get_statement",
    "statement_execution.cancel_execution",
}


@pytest.mark.parametrize("name", list(_scenarios()))
def test_ac198_only_read_calls_before_the_first_drop_and_no_secret_in_output(
    capsys: pytest.CaptureFixture[str], name: str
) -> None:
    client, argv, factory = _scenarios()[name]
    code, lines, everything = invoke(capsys, client, argv, factory=factory)
    assert code in (0, 1, 2)
    assert client.forbidden == []
    assert set(client.called) <= READ_ONLY
    assert "pipelines.get" not in client.called
    statements = client.statements()
    before_drop = statements[
        : next((i for i, s in enumerate(statements) if s.startswith("DROP")), None)
    ]
    assert all(s.startswith("SELECT") for s in before_drop)
    for line in lines:
        assert fakes.no_secret(line), line
    if name == "secret":
        assert "<redacted>" in lines[0]
        assert "denied" in lines[0]


# ----------------------------------------------------------------------------- AC-199
def _git_status() -> str:
    return subprocess.run(  # noqa: S603
        ["git", "status", "--porcelain", "--untracked-files=all"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def test_ac199_two_runs_give_equal_output_and_change_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cases = {
        "busy": (lambda: busy_client(101, "RUNNING"), ["--confirm"], None),
        "denied": (
            lambda: fakes.FakeClient(overrides={"jobs.get": fakes.PermissionDenied()}),
            ["--confirm"],
            None,
        ),
        "empty warehouse list": (lambda: fakes.FakeClient(warehouses=[]), [], None),
        "idle dry run": (lambda: fakes.FakeClient(), [], None),
    }
    before = _git_status()
    for name, (build, argv, factory) in cases.items():
        first_client, second_client = build(), build()
        first = invoke(capsys, first_client, argv, factory=factory)
        second = invoke(capsys, second_client, argv, factory=factory)
        assert first == second, name
        assert first_client.log == second_client.log
        if first[0] == 2:
            assert all(s.startswith("SELECT") for s in first_client.statements())
    assert _git_status() == before


# ----------------------------------------------------------------------------- AC-200
def _budget_clients() -> dict[str, tuple[fakes.FakeClient, Any]]:
    clients: dict[str, tuple[fakes.FakeClient, Any]] = {
        "busy peak": (busy_client(101, "RUNNING"), None),
        "busy training": (busy_client(102, "RUNNING"), None),
        "idle": (fakes.FakeClient(), None),
    }
    for case in AC190_CASES:
        clients[f"ac190 {case}"] = ac190_client(case)
    return clients


@pytest.mark.parametrize("name", list(_budget_clients()))
def test_ac200_idle_check_reads_at_most_4_calls_per_job_and_never_sleeps(
    capsys: pytest.CaptureFixture[str], clean_environment: list[float], name: str
) -> None:
    client, factory = _budget_clients()[name]
    invoke(capsys, client, ["--confirm"], factory=factory)
    entries = client.jobs_entries()
    assert len(entries) <= 8
    if name == "idle":
        assert entries == IDLE_READS
    assert clean_environment == []


def test_ac200_runs_read_are_capped_at_25_per_job(capsys: pytest.CaptureFixture[str]) -> None:
    many = [fakes.run("RUNNING", run_id=i) for i in range(1, 31)]
    client = fakes.FakeClient(runs={101: many, 102: list(many)})
    code, lines, _ = invoke(capsys, client, [])
    assert code == 2
    assert len(lines) == 1
    assert client.pulled["runs:101"] == client.pulled["runs:102"] == pipeline_guard.MAX_RUNS_READ


def _fake_sdk(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    class Config:
        def __init__(self, **options: Any) -> None:
            captured["config"] = options

    class WorkspaceClient:
        def __init__(self, config: Any = None) -> None:
            captured["client"] = config

    sdk, config = ModuleType("databricks.sdk"), ModuleType("databricks.sdk.config")
    sdk.WorkspaceClient = WorkspaceClient  # type: ignore[attr-defined]
    config.Config = Config  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "databricks", ModuleType("databricks"))
    monkeypatch.setitem(sys.modules, "databricks.sdk", sdk)
    monkeypatch.setitem(sys.modules, "databricks.sdk.config", config)
    return captured


def test_ac200_client_is_built_with_the_shipped_limits(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _fake_sdk(monkeypatch)
    built = reset.build_client()
    assert isinstance(built, sys.modules["databricks.sdk"].WorkspaceClient)
    assert captured["config"] == {"retry_timeout_seconds": 60, "http_timeout_seconds": 30}
    assert captured["config"] == dict(pipeline_guard.CLIENT_LIMITS)
    monkeypatch.setenv("DATABRICKS_CONFIG_PROFILE", "dev")
    reset.build_client()
    assert captured["config"] == {
        "retry_timeout_seconds": 60,
        "http_timeout_seconds": 30,
        "profile": "dev",
    }
    assert isinstance(captured["client"], sys.modules["databricks.sdk.config"].Config)

    client = fakes.FakeClient()
    code, _, _ = invoke(capsys, client, ["--confirm"])
    assert code == 0
    assert client.waits
    assert set(client.waits) == {"20s"}


@pytest.mark.parametrize(
    ("options", "text"),
    [
        (
            {"sql": {FEATURES_COUNT: "FAILED:[SERVER] down"}},
            "row counts: SQL failed: [SERVER] down",
        ),
        (
            {"overrides": {"statement_execution.get_statement": RuntimeError("x")}, "sql": {}},
            None,
        ),
    ],
)
def test_ac192_a_failed_count_query_is_labelled_row_counts(
    capsys: pytest.CaptureFixture[str], options: dict[str, Any], text: str | None
) -> None:
    if text is None:
        options = {"overrides": {"statement_execution.execute_statement": _count_raises()}}
        text = "row counts: RuntimeError: count down"
    client = fakes.FakeClient(**options)
    code, lines, everything = invoke(capsys, client, ["--confirm"])
    line = one_refusal(code, lines, everything)
    assert line.startswith(PREFIX + text) or f"; {text}" in line or text in line
    assert client.drops() == []


def _count_raises() -> Any:
    def call(**kwargs: Any) -> Any:
        if kwargs["statement"].startswith("SELECT count(*)"):
            raise RuntimeError("count down")
        return SimpleNamespace(
            statement_id="s",
            status=SimpleNamespace(state="SUCCEEDED", error=None),
            result=SimpleNamespace(data_array=[["UTC"]]),
        )

    return call
