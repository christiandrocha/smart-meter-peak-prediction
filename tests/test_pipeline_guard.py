"""Pre-check before the shared pipeline task (AC-69 to AC-73; G-13 to G-20, ADR 0012).

The guard runs against a recording fake workspace that exposes the read methods of
``pipeline_guard.READ_CALLS`` only; any other attribute is recorded and raises.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from types import SimpleNamespace
from typing import Any

import pytest

from smart_meter_peak_prediction import pipeline_guard as pg

NOW = datetime(2026, 10, 23, 8, 0, 41, tzinfo=UTC)
NOW_TEXT = "2026-10-23T08:00:41Z"
JOB_ID = 123456789
PIPELINE_ID = "0a1b2c3d-pipeline"
RUN_ID = 1002990004411119
UPDATE_ID = "3c4d5e6f-update"
DEV_JOB = "[dev someone] smart_meter_ingestion"
DEV_PIPELINE = "[dev someone] smart_meter_silver_gold"
UTC_SHAPE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}[\w:.+\-]*")
UTC_OK = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")

NON_TERMINAL_RUN_STATES = ["QUEUED", "PENDING", "RUNNING", "TERMINATING", "BLOCKED"]
NON_TERMINAL_UPDATE_STATES = [
    "CREATED",
    "QUEUED",
    "INITIALIZING",
    "RESETTING",
    "SETTING_UP_TABLES",
    "RUNNING",
    "STOPPING",
    "WAITING_FOR_RESOURCES",
]


class ApiError(Exception):
    """Carries ``error_code`` as the SDK errors do."""

    def __init__(self, message: str, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class PermissionDenied(ApiError):
    def __init__(self, message: str = "no access to the job") -> None:
        super().__init__(message, "PERMISSION_DENIED")


class NotFound(ApiError):
    def __init__(self, message: str = "does not exist") -> None:
        super().__init__(message, "RESOURCE_DOES_NOT_EXIST")


class RunState(Enum):
    RUNNING = "RUNNING"


def run_obj(
    state: Any = "RUNNING", run_id: int = RUN_ID, start_time: Any = 1792742282000
) -> SimpleNamespace:
    return SimpleNamespace(
        run_id=run_id, state=SimpleNamespace(life_cycle_state=state), start_time=start_time
    )


def update_obj(
    state: Any = "RUNNING",
    update_id: str = UPDATE_ID,
    creation_time: Any = "2026-10-23T07:59:10.206Z",
) -> SimpleNamespace:
    return SimpleNamespace(update_id=update_id, state=state, creation_time=creation_time)


class _Api:
    def __init__(self, fake: FakeWorkspace, name: str) -> None:
        self._fake = fake
        self._name = name

    def __getattr__(self, method: str) -> Any:
        key = f"{self._name}.{method}"
        if key not in pg.READ_CALLS:
            self._fake.forbidden.append(key)
            raise AssertionError(f"forbidden call {key}")

        def call(**kwargs: Any) -> Any:
            self._fake.calls.append((self._name, method, kwargs))
            handler = self._fake.handlers[key]
            if isinstance(handler, Exception):
                raise handler
            return handler(**kwargs) if callable(handler) else handler

        return call


@dataclass
class FakeWorkspace:
    """Recording fake: ``handlers`` map ``api.method`` to a value, a callable or an exception."""

    handlers: dict[str, Any]

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.forbidden: list[str] = []
        self.jobs = _Api(self, "jobs")
        self.pipelines = _Api(self, "pipelines")


def workspace(
    *,
    runs: list[Any] | None = None,
    updates: list[Any] | None = None,
    job_name: str = DEV_JOB,
    same_name: list[int] | None = None,
    pipeline_name: str = DEV_PIPELINE,
    pipeline_state: str | None = "IDLE",
    overrides: dict[str, Any] | None = None,
) -> FakeWorkspace:
    handlers: dict[str, Any] = {
        "jobs.get": SimpleNamespace(job_id=JOB_ID, settings=SimpleNamespace(name=job_name)),
        "jobs.list": [
            SimpleNamespace(job_id=i) for i in (same_name if same_name is not None else [JOB_ID])
        ],
        "jobs.list_runs": runs or [],
        "pipelines.get": SimpleNamespace(
            name=pipeline_name,
            state=SimpleNamespace(value=pipeline_state) if pipeline_state else None,
            latest_updates=updates,
        ),
    }
    handlers.update(overrides or {})
    return FakeWorkspace(handlers)


def check(
    fake: FakeWorkspace, job_id: Any = JOB_ID, pipeline_id: Any = PIPELINE_ID
) -> pg.GuardReport:
    return pg.check(fake, job_id, pipeline_id, now=NOW)


def assert_read_only(fake: FakeWorkspace) -> None:
    assert fake.forbidden == []
    assert {f"{api}.{method}" for api, method, _ in fake.calls} <= set(pg.READ_CALLS)


def assert_times_are_utc(message: str) -> None:
    for found in UTC_SHAPE.findall(message):
        assert UTC_OK.fullmatch(found), found


# ----------------------------------------------------------------------------- AC-69
@pytest.mark.parametrize(
    "state", [*NON_TERMINAL_RUN_STATES, "WAITING_FOR_RETRY", "A_FUTURE_STATE", RunState.RUNNING]
)
def test_ac69_active_ingestion_run_fails_with_job_run_id_and_action(state: Any) -> None:
    fake = workspace(runs=[run_obj(state)])
    report = check(fake)
    assert not report.ok
    with pytest.raises(pg.PipelineGuardError) as raised:
        pg.enforce(report)
    message = str(raised.value)
    assert "smart_meter_ingestion" in message
    assert str(RUN_ID) in message
    assert f"job id {JOB_ID}" in message
    assert "rerun smart_meter_peak_model" in message
    assert "08:00 UTC" in message
    assert "started 2026-10-23T07:58:02Z" in message
    assert_times_are_utc(message)
    assert_read_only(fake)


def test_ac69_queued_run_without_start_time_reads_not_started() -> None:
    report = check(workspace(runs=[run_obj("QUEUED", start_time=None)]))
    assert "started not started" in report.message()
    assert_times_are_utc(report.message())


def test_ac69_listed_run_in_a_terminal_state_does_not_block() -> None:
    fake = workspace(
        runs=[run_obj("TERMINATED"), run_obj("SKIPPED", 2), run_obj("INTERNAL_ERROR", 3)]
    )
    report = check(fake)
    assert report.ok
    assert report.runs == ()


def test_ac69_at_most_25_runs_are_read() -> None:
    fake = workspace(runs=[run_obj("RUNNING", run_id=i) for i in range(1, 60)])
    report = check(fake)
    assert len(report.runs) == pg.MAX_RUNS_READ == 25


def test_ac69_state_constants_match_the_sdk_enums() -> None:
    jobs = pytest.importorskip("databricks.sdk.service.jobs")
    pipelines = pytest.importorskip("databricks.sdk.service.pipelines")
    run_states = {member.value for member in jobs.RunLifeCycleState}
    assert pg.TERMINAL_RUN_STATES <= run_states
    for member in run_states - pg.TERMINAL_RUN_STATES:
        assert check(workspace(runs=[run_obj(member)])).runs, member
    update_enum = getattr(pipelines, "UpdateInfoState", None) or pipelines.UpdateStateInfoState
    update_states = {member.value for member in update_enum}
    assert pg.TERMINAL_UPDATE_STATES <= update_states
    for member in update_states - pg.TERMINAL_UPDATE_STATES:
        assert check(workspace(updates=[update_obj(member)])).updates, member
    pipeline_states = {member.value for member in pipelines.PipelineState}
    assert pg.PASS_PIPELINE_STATES <= pipeline_states
    assert pg.ACTIVE_PIPELINE_STATES <= pipeline_states
    assert pg.UNUSABLE_PIPELINE_STATE in pipeline_states
    for member in pipeline_states - pg.PASS_PIPELINE_STATES - {pg.UNUSABLE_PIPELINE_STATE}:
        assert check(workspace(pipeline_state=member)).pipeline_busy, member
    # the real enum members are read through .value
    assert check(workspace(runs=[run_obj(jobs.RunLifeCycleState.RUNNING)])).runs
    assert check(workspace(runs=[run_obj(jobs.RunLifeCycleState.TERMINATED)])).ok


# ----------------------------------------------------------------------------- AC-70
@pytest.mark.parametrize("state", [*NON_TERMINAL_UPDATE_STATES, "A_FUTURE_STATE", None])
def test_ac70_update_state_decides_the_outcome_when_active(state: str | None) -> None:
    fake = workspace(updates=[update_obj(state)])
    report = check(fake)
    assert not report.ok
    with pytest.raises(pg.PipelineGuardError) as raised:
        pg.enforce(report)
    message = str(raised.value)
    assert "smart_meter_silver_gold" in message
    assert UPDATE_ID in message
    assert (state or "UNKNOWN") in message
    assert f"pipeline id {PIPELINE_ID}" in message
    assert "created 2026-10-23T07:59:10Z" in message
    assert_times_are_utc(message)
    assert_read_only(fake)


@pytest.mark.parametrize("state", ["COMPLETED", "FAILED", "CANCELED"])
def test_ac70_update_state_decides_the_outcome_when_terminal(state: str) -> None:
    report = check(workspace(updates=[update_obj(state)]))
    assert report.ok
    value = pg.enforce(report)
    assert value["outcome"] == "idle"
    assert value["pipeline"]["latest_update"] == {"update_id": UPDATE_ID, "state": state}


def test_ac70_creation_time_is_printed_in_utc_or_not_at_all() -> None:
    expected = "2026-10-22T17:54:05Z"
    assert pg.utc_text("2026-10-22T17:54:05.206Z") == expected  # the platform form (DA-22)
    assert pg.utc_text("2026-10-22T17:54:05Z") == expected
    assert pg.utc_text("2026-10-22T19:54:05+02:00") == expected
    assert pg.utc_text("2026-10-22T17:54:05+00:00") == expected
    epoch_ms = int(datetime(2026, 10, 22, 17, 54, 5, tzinfo=UTC).timestamp() * 1000)
    assert pg.utc_text(epoch_ms) == expected
    assert pg.utc_text(str(epoch_ms)) == expected
    assert pg.utc_text(datetime(2026, 10, 22, 17, 54, 5, tzinfo=UTC)) == expected
    for bad in ("2026-10-22T17:54:05", "2026-10-22 17:54:05", "garbage", "", None, 0, True):
        assert pg.utc_text(bad) is None, bad
    report = check(workspace(updates=[update_obj("RUNNING", creation_time="2026-10-22T17:54:05")]))
    assert "creation time not reported" in report.message()
    assert_times_are_utc(report.message())


@pytest.mark.parametrize("updates", [[], [update_obj("COMPLETED")]])
@pytest.mark.parametrize(
    "state",
    ["RUNNING", "DEPLOYING", "STARTING", "STOPPING", "RECOVERING", "RESETTING", "A_FUTURE_STATE"],
)
def test_ac70_pipeline_state_decides_the_outcome(state: str, updates: list[Any]) -> None:
    fake = workspace(updates=updates, pipeline_state=state)
    report = check(fake)
    assert not report.ok
    with pytest.raises(pg.PipelineGuardError) as raised:
        pg.enforce(report)
    message = str(raised.value)
    assert "smart_meter_silver_gold" in message
    assert f"pipeline state {state}, no active update listed in latest_updates" in message
    assert UPDATE_ID not in message
    assert report.exit_value()["outcome"] == "busy"
    assert_times_are_utc(message)
    assert_read_only(fake)


@pytest.mark.parametrize("state", ["IDLE", "FAILED"])
def test_ac70_pipeline_pass_states_succeed(state: str) -> None:
    report = check(workspace(updates=[update_obj("COMPLETED")], pipeline_state=state))
    assert report.ok
    assert pg.enforce(report)["pipeline"]["state"] == state


def test_ac70_missing_pipeline_state_fails_closed() -> None:
    report = check(workspace(updates=[update_obj("COMPLETED")], pipeline_state=None))
    assert not report.ok
    message = report.message()
    assert "pipeline state not reported, no active update listed in latest_updates" in message


def test_ac70_active_update_names_the_update_and_the_pipeline_state() -> None:
    busy = check(workspace(updates=[update_obj("RUNNING")], pipeline_state="RUNNING"))
    line = [ln for ln in busy.message().splitlines() if UPDATE_ID in ln]
    assert len(line) == 1
    assert "pipeline state RUNNING" in line[0]
    assert "no active update listed" not in busy.message()
    # an active update blocks even when the pipeline state reads IDLE (G-17)
    idle_state = check(workspace(updates=[update_obj("RUNNING")], pipeline_state="IDLE"))
    assert not idle_state.ok
    assert "pipeline state IDLE" in idle_state.message()


# ----------------------------------------------------------------------------- AC-71
def test_ac71_both_blockers_are_named() -> None:
    report = check(workspace(runs=[run_obj()], updates=[update_obj()]))
    assert not report.ok
    with pytest.raises(pg.PipelineGuardError) as raised:
        pg.enforce(report)
    lines = str(raised.value).splitlines()
    run_lines = [line for line in lines if str(RUN_ID) in line]
    update_lines = [line for line in lines if UPDATE_ID in line]
    assert len(run_lines) == 1
    assert len(update_lines) == 1
    assert run_lines[0] != update_lines[0]
    assert_times_are_utc(str(raised.value))


def test_ac71_active_run_and_busy_pipeline_state_are_both_named() -> None:
    report = check(
        workspace(runs=[run_obj()], updates=[update_obj("COMPLETED")], pipeline_state="RUNNING")
    )
    lines = report.message().splitlines()
    assert len([line for line in lines if str(RUN_ID) in line]) == 1
    assert len([line for line in lines if "no active update listed" in line]) == 1


# ----------------------------------------------------------------------------- AC-72
@pytest.mark.parametrize(
    "updates",
    [[], None, [update_obj("COMPLETED")], [update_obj("FAILED"), update_obj("COMPLETED")]],
)
def test_ac72_idle_state_succeeds_twice_with_read_calls_only(updates: list[Any] | None) -> None:
    fake = workspace(updates=updates)
    first = check(fake)
    second = check(fake)
    assert first.ok
    assert first == second
    assert pg.enforce(first) == pg.enforce(second)
    value = pg.enforce(first)
    assert value["outcome"] == "idle"
    assert value["checked_at"] == NOW_TEXT
    assert value["ingestion_job"] == {
        "job_id": JOB_ID,
        "name": "smart_meter_ingestion",
        "active_runs": [],
    }
    assert value["pipeline"]["name"] == "smart_meter_silver_gold"
    assert value["pipeline"]["state"] == "IDLE"
    later = pg.check(fake, JOB_ID, PIPELINE_ID, now=datetime(2026, 10, 24, 8, 0, 3, tzinfo=UTC))
    other = pg.enforce(later)
    assert other.pop("checked_at") == "2026-10-24T08:00:03Z"
    assert other == {k: v for k, v in value.items() if k != "checked_at"}
    assert_read_only(fake)
    assert len(fake.calls) == 4 * 3  # one read per object and call, no loop


def test_ac72_one_read_per_object_without_waiting() -> None:
    fake = workspace()
    check(fake)
    assert [f"{api}.{method}" for api, method, _ in fake.calls] == [
        "jobs.get",
        "jobs.list",
        "jobs.list_runs",
        "pipelines.get",
    ]
    assert fake.calls[2][2] == {"job_id": JOB_ID, "active_only": True}


def test_ac72_client_limits_are_config_keywords_and_module_is_sdk_free() -> None:
    assert pg.CLIENT_LIMITS == {"retry_timeout_seconds": 60, "http_timeout_seconds": 30}
    source = open(pg.__file__, encoding="utf-8").read()  # noqa: SIM115
    assert "import databricks" not in source
    assert "from databricks" not in source


# ----------------------------------------------------------------------------- AC-73
def _factory_raises() -> Any:
    raise ConnectionError("cannot reach the workspace")


CASES: dict[str, Any] = {
    "job id not found": (dict(overrides={"jobs.get": NotFound()}), {}, "job"),
    "job name list has two": (dict(same_name=[JOB_ID, 7]), {}, "not unique"),
    "job name list is empty": (dict(same_name=[]), {}, "not unique"),
    "job id names another job": (dict(job_name="[dev someone] other_job"), {}, "another job"),
    "pipeline id not found": (dict(overrides={"pipelines.get": NotFound()}), {}, "pipeline"),
    "pipeline id names another": (dict(pipeline_name="other"), {}, "another pipeline"),
    "list_runs raises": (
        dict(overrides={"jobs.list_runs": RuntimeError("boom")}),
        {},
        "active runs",
    ),
    "pipelines.get denied": (
        dict(overrides={"pipelines.get": PermissionDenied()}),
        {},
        "PERMISSION_DENIED",
    ),
    "jobs.list raises": (dict(overrides={"jobs.list": RuntimeError("down")}), {}, "job name list"),
    "empty job id": ({}, {"job_id": ""}, "id missing or not resolved"),
    "empty pipeline id": ({}, {"pipeline_id": ""}, "id missing or not resolved"),
    "unresolved job id": ({}, {"job_id": "${resources.jobs.x.id}"}, "not resolved"),
    "unresolved pipeline id": ({}, {"pipeline_id": "${resources.pipelines.x.id}"}, "not resolved"),
    "non-integer job id": ({}, {"job_id": "abc"}, "id missing or not resolved"),
    "zero job id": ({}, {"job_id": "0"}, "id missing or not resolved"),
}


@pytest.mark.parametrize("case", list(CASES))
def test_ac73_unreadable_state_fails_closed(case: str) -> None:
    build, ids, expected = CASES[case]
    fake = workspace(**build)
    report = check(fake, ids.get("job_id", JOB_ID), ids.get("pipeline_id", PIPELINE_ID))
    assert not report.ok
    assert report.unreadable
    with pytest.raises(pg.PipelineGuardError) as raised:
        pg.enforce(report)
    message = str(raised.value)
    assert "fails closed" in message
    assert "Could not read" in message
    assert expected in message
    assert "smart_meter_ingestion" in message or "smart_meter_silver_gold" in message
    assert "08:00 UTC" in message
    assert_times_are_utc(message)
    assert_read_only(fake)


def test_ac73_deleted_pipeline_fails_closed_as_unusable() -> None:
    report = check(workspace(updates=[update_obj("COMPLETED")], pipeline_state="DELETED"))
    assert not report.ok
    assert not report.pipeline_busy
    message = report.message()
    assert "could not establish the pipeline state and fails closed" in message
    assert "pipeline state: DELETED, not usable" in message
    assert report.exit_value()["outcome"] == "unknown"


def test_ac73_client_factory_failure_is_unreadable_for_both_objects() -> None:
    report = pg.run(_factory_raises, JOB_ID, PIPELINE_ID, now=NOW)
    assert not report.ok
    with pytest.raises(pg.PipelineGuardError) as raised:
        pg.enforce(report)
    message = str(raised.value)
    assert "smart_meter_ingestion" in message
    assert "smart_meter_silver_gold" in message
    assert "ConnectionError" in message
    assert "workspace client" in message


def test_ac73_run_with_a_working_factory_checks_the_workspace() -> None:
    fake = workspace()
    report = pg.run(lambda: fake, str(JOB_ID), PIPELINE_ID, now=NOW)
    assert report.ok


def test_ac73_error_text_is_one_short_line_without_secrets() -> None:
    long_error = PermissionDenied(
        "first line " + "x" * 400 + "\nAuthorization: Bearer abc123\nmore"
    )
    report = check(workspace(overrides={"jobs.list_runs": long_error}))
    message = report.message()
    assert "Bearer" not in message
    assert "abc123" not in message
    line = next(line for line in message.splitlines() if "active runs" in line)
    assert "PermissionDenied (PERMISSION_DENIED): first line" in line
    assert len(line.split("(PERMISSION_DENIED): ", 1)[1]) <= pg.MAX_ERROR_CHARS
    assert_times_are_utc(message)


def test_ac73_blockers_and_unreadable_items_are_both_reported() -> None:
    fake = workspace(
        runs=[run_obj()], overrides={"pipelines.get": PermissionDenied("no pipeline access")}
    )
    message = check(fake).message()
    assert "Blocking:" in message
    assert "Could not read:" in message
    assert str(RUN_ID) in message
    assert "no pipeline access" in message


def test_ac73_unreadable_job_does_not_hide_a_busy_pipeline() -> None:
    fake = workspace(updates=[update_obj()], overrides={"jobs.get": NotFound()})
    report = check(fake)
    assert report.updates
    assert report.unreadable
    assert UPDATE_ID in report.message()


def test_ac73_forbidden_calls_are_recorded_and_raise() -> None:
    fake = workspace()
    with pytest.raises(AssertionError):
        fake.jobs.run_now(job_id=1)
    with pytest.raises(AssertionError):
        fake.pipelines.start_update(pipeline_id="x")
    assert fake.forbidden == ["jobs.run_now", "pipelines.start_update"]


def test_ac73_secret_like_text_on_the_first_line_is_redacted() -> None:
    error = RuntimeError("call to https://host.example/api failed: Bearer abc123 dapi0123456789")
    message = check(workspace(overrides={"jobs.list_runs": error})).message()
    for leaked in ("host.example", "abc123", "dapi0123456789"):
        assert leaked not in message
    assert "<redacted>" in message


def test_ac73_client_limits_are_accepted_by_the_sdk_config() -> None:
    config_module = pytest.importorskip("databricks.sdk.config")
    config = config_module.Config(host="https://example.invalid", token="x", **pg.CLIENT_LIMITS)  # noqa: S106
    assert config.retry_timeout_seconds == 60
    assert config.http_timeout_seconds == 30


def test_ac73_edge_inputs_fail_closed_or_are_active() -> None:
    nameless = workspace(
        overrides={"jobs.get": SimpleNamespace(settings=SimpleNamespace(name=None))}
    )
    assert not check(nameless).ok
    stateless = SimpleNamespace(run_id=5, state=None, start_time=None)
    report = check(workspace(runs=[stateless]))
    assert report.runs[0].state == "UNKNOWN"
    no_id = check(workspace(updates=[SimpleNamespace(state="RUNNING", creation_time=None)]))
    assert no_id.updates[0].update_id == "unknown"
    prod = workspace(job_name="smart_meter_ingestion", pipeline_name="smart_meter_silver_gold")
    assert check(prod).ok  # no development prefix on the prod target
